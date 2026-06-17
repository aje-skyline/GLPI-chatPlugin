"""app/services/conversational_flow.py — Event-Driven Conversational Flow."""

import asyncio
import logging
from typing import List, Dict

from pydantic import BaseModel
from crewai.flow.flow import Flow, start, listen

from app.services.crew_orchestrator import run_crew_async

logger = logging.getLogger(__name__)

class ConversationalState(BaseModel):
    user_id: int = 0
    current_message: str = ""
    history: List[Dict[str, str]] = []
    final_output: str = ""

class ConversationalFlow(Flow[ConversationalState]):
    """Event-Driven Conversational Flow for GLPI Chatbot using CrewAI."""

    @start()
    def initialize_interaction(self):
        """Inisialisasi interaksi dan tambahkan pesan user ke riwayat."""
        logger.info(f"Initialize interaction for user_id: {self.state.user_id}")
        if self.state.current_message:
            # Pastikan pesan user terbaru masuk ke history jika belum ada
            if not self.state.history or self.state.history[-1].get("role") != "user" or self.state.history[-1].get("content") != self.state.current_message:
                self.state.history.append({"role": "user", "content": self.state.current_message})
        return self.state.current_message

    @listen(initialize_interaction)
    async def trigger_crew_agent(self, user_message: str):
        """Memicu eksekusi Crew Agent secara asinkron menggunakan kickoff_async."""
        logger.info("Triggering Crew Agent asynchronously...")
        
        # Menggunakan run_crew_async yang secara internal memanggil crew.kickoff_async()
        result = await run_crew_async(
            user_message=self.state.current_message,
            glpi_user_id=self.state.user_id,
            messages=self.state.history
        )
        
        # Menyimpan output dan menambahkan ke history
        self.state.final_output = result
        self.state.history.append({"role": "assistant", "content": result})
        
        return result
