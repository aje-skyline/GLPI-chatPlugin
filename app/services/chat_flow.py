"""app/services/chat_flow.py — Conversational Flow using CrewAI."""

import uuid
import logging
from typing import List, Dict, Any

from pydantic import BaseModel
from crewai.flow.flow import Flow, listen, start, router
from crewai.flow.persistence import persist
from litellm import completion

from app.config import settings
from app.services.crew_orchestrator import run_crew, run_crew_async

logger = logging.getLogger(__name__)

class GLPIChatState(BaseModel):
    id: str = ""
    glpi_user_id: int = 0
    current_message: str = ""
    conversation_history: List[Dict[str, str]] = []
    final_response: str = ""
    is_streaming: bool = False

@persist()
class GLPIChatFlow(Flow[GLPIChatState]):
    """Conversational flow for handling GLPI queries vs casual pleasantries."""

    @start()
    def init_chat(self):
        """Initialize chat session."""
        if not self.state.id:
            self.state.id = uuid.uuid4().hex
            
        logger.info(f"Starting chat flow for session: {self.state.id}, msg: '{self.state.current_message[:30]}...'")
        
        # If the user passed history manually (from main.py merge), we can use it.
        # But if we rely fully on @persist(), self.state.conversation_history might be loaded automatically
        # by CrewAI Enterprise / persistence (if we implement a proper state loader). 
        # For now, we trust the caller has updated the state with the latest message.
        return self.state.current_message

    @router(init_chat)
    def classify_message(self):
        """Classify message as 'casual' or 'technical'."""
        if not self.state.current_message.strip():
            return "casual"
            
        messages = [
            {
                "role": "system", 
                "content": "You are a message classifier. Reply with exactly 'casual' if the user's message is a simple greeting, thanks, or pleasantry with no IT, GLPI, or technical context. Otherwise, reply 'technical'."
            },
            {"role": "user", "content": self.state.current_message}
        ]
        
        try:
            response = completion(
                model=f"openai/{settings.ai_model}",
                api_key=settings.ai_gateway_api_key,
                api_base=settings.resolved_ai_gateway_base_url,
                messages=messages,
                temperature=0.0,
                max_tokens=10
            )
            classification = response.choices[0].message.content.strip().lower()
            if "casual" in classification:
                logger.info("Message classified as casual")
                return "casual"
        except Exception as e:
            logger.warning(f"Classification failed, defaulting to technical: {e}")
            
        logger.info("Message classified as technical")
        return "technical"

    @listen("casual")
    def handle_casual(self):
        """Handle casual messages simply and directly."""
        messages = [
            {
                "role": "system", 
                "content": "You are a helpful IT support assistant for GLPI. Respond briefly to greetings or pleasantries in Indonesian."
            }
        ] + self.state.conversation_history + [
            {"role": "user", "content": self.state.current_message}
        ]
        
        try:
            response = completion(
                model=f"openai/{settings.ai_model}",
                api_key=settings.ai_gateway_api_key,
                api_base=settings.resolved_ai_gateway_base_url,
                messages=messages,
                temperature=0.7,
                max_tokens=250
            )
            self.state.final_response = response.choices[0].message.content.strip()
        except Exception as e:
            self.state.final_response = f"Mohon maaf, terjadi kesalahan: {e}"

    @listen("technical")
    def handle_technical(self):
        """Handle technical GLPI queries using CrewAI."""
        # Here we connect to the existing run_crew logic
        if self.state.is_streaming:
            # We defer streaming execution to main.py, so we just set a flag or throw/return
            # Usually in streaming, we run_crew_async directly, but for flow we might
            # not block here. For this implementation, we will assume handle_technical
            # generates the final answer synchronously if it's called inside the flow natively.
            pass
            
        # Call the orchestrator
        answer = run_crew(
            user_message=self.state.current_message,
            glpi_user_id=self.state.glpi_user_id,
            messages=self.state.conversation_history
        )
        self.state.final_response = answer
