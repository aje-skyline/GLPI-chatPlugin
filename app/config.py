"""Application configuration using Pydantic Settings.

Reads from .env file and environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralized settings for GLPI AI Gateway.

    Attributes:
        ai_gateway_url: Full URL for AI Gateway (e.g., https://ai-gw/v1/chat/completions)
        ai_gateway_base_url: Base URL without endpoint suffix (optional, auto-resolved)
        ai_gateway_api_key: API key for authenticating to AI Gateway
        nemotron_model: Model name for CrewAI via LiteLLM (prefix with "openai/")
        gateway_api_key: Bearer token for this FastAPI service
        allowed_origins: CORS allowed origins (comma-separated)
        glpi_url: Base URL for GLPI instance
        glpi_app_token: GLPI application token
        glpi_user_token: GLPI user token for session init
    """

    # Konfigurasi utama
    mock_mode: bool = False
    crew_verbose: bool = False
    
    #Provider Selection
    llm_provider: str = "openai"
    llm_model: str= "gpt-5-mini"

    # AI Gateway (Nemotron)
    ai_gateway_url: str
    ai_gateway_base_url: str = ""
    ai_gateway_api_key: str

    # Model for CrewAI
    ai_model: str = "gpt-5-mini"

    # FastAPI Gateway security
    gateway_api_key: str
    allowed_origins: str = "http://172.16.14.141"

    # GLPI API
    glpi_url: str = "https://172.16.14.141"
    glpi_app_token: str = ""
    glpi_user_token: str = ""
    glpi_api_url: str = "https://172.16.14.141/asset/apirest.php"

    # SSL
    glpi_verify_ssl: bool = False
    
    # Session config
    session_ttl_minutes: int = 60

    model_config = {"env_file": ".env"}

    @property
    def resolved_ai_gateway_base_url(self) -> str:
        """Resolve base URL for AI Gateway.

        LiteLLM appends /chat/completions automatically, so we strip it if present.
        Falls back to ai_gateway_url with suffix removed.
        """
        if self.ai_gateway_base_url:
            return self.ai_gateway_base_url.rstrip("/")
        base = self.ai_gateway_url
        for suffix in ["/v1/chat/completions", "/chat/completions"]:
            if base.endswith(suffix):
                return base[: -len(suffix)].rstrip("/")
        return base.rstrip("/")


settings = Settings()