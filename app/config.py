"""Application configuration — GLPI AI Gateway.

Membaca konfigurasi dari file .env dan environment variables
menggunakan Pydantic Settings.

Semua field LLM merujuk ke AI Gateway kustom yang kompatibel dengan
OpenAI API spec. Tidak ada konfigurasi LiteLLM atau LangChain di sini
— CrewAI menangani pemetaan provider secara internal via prefix "openai/".
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Konfigurasi terpusat GLPI AI Gateway.

    Attributes:
        mock_mode             : Jika True, skip panggilan GLPI/LLM (untuk testing).
        crew_verbose          : Aktifkan logging verbose CrewAI.
        ai_gateway_url        : URL lengkap AI Gateway (mis. https://ai-gw/v1/chat/completions).
        ai_gateway_base_url   : Base URL tanpa suffix endpoint (opsional, auto-resolved).
        ai_gateway_api_key    : API key untuk autentikasi ke AI Gateway.
        ai_model              : Nama model lengkap (termasuk prefix provider), mis. "qwen/qwen3-next-80b-a3b-instruct".
        gateway_api_key       : Bearer token untuk mengamankan endpoint FastAPI ini.
        allowed_origins       : CORS allowed origins (comma-separated).
        glpi_url              : Base URL instance GLPI.
        glpi_app_token        : GLPI application token.
        glpi_user_token       : GLPI user token untuk inisialisasi sesi.
        glpi_api_url          : URL lengkap GLPI REST API.
        glpi_verify_ssl       : Verifikasi SSL certificate GLPI (set False untuk self-signed).
        session_ttl_minutes   : Durasi session in-memory sebelum di-cleanup.
    """

    # ── Runtime flags ──────────────────────────────────────────────────────────
    mock_mode: bool    = False
    crew_verbose: bool = False

    # ── AI Gateway / LLM ───────────────────────────────────────────────────────
    # Konfigurasi untuk AI Gateway kustom kompatibel OpenAI.
    # Prefix provider ("openai/") ditambahkan di crew_services.py saat
    # membuat instance crewai.LLM — tidak perlu disimpan di sini.
    ai_gateway_url: str
    ai_gateway_base_url: str = ""
    ai_gateway_api_key: str
    ai_model: str = "qwen/qwen3-next-80b-a3b-instruct"

    # ── FastAPI Gateway security ───────────────────────────────────────────────
    gateway_api_key: str
    allowed_origins: str = "http://172.16.14.141"

    # ── GLPI REST API ──────────────────────────────────────────────────────────
    glpi_url: str       = "https://172.16.14.141"
    glpi_app_token: str = ""
    glpi_user_token: str = ""
    glpi_api_url: str   = "https://172.16.14.103/asset/apirest.php"
    glpi_verify_ssl: bool = False

    # ── Session store ──────────────────────────────────────────────────────────
    session_ttl_minutes: int = 60

    model_config = {"env_file": ".env"}

    @property
    def resolved_ai_gateway_base_url(self) -> str:
        """Resolve base URL untuk CrewAI LLM.

        LiteLLM (internal CrewAI) menambahkan /chat/completions secara
        otomatis, jadi suffix tersebut perlu di-strip jika ada.

        Returns:
            Base URL bersih tanpa trailing slash dan tanpa suffix endpoint.
        """
        if self.ai_gateway_base_url:
            return self.ai_gateway_base_url.rstrip("/")

        base = self.ai_gateway_url
        for suffix in ("/v1/chat/completions", "/chat/completions"):
            if base.endswith(suffix):
                return base[: -len(suffix)].rstrip("/")
        return base.rstrip("/")


settings = Settings()