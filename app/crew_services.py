"""CrewAI orchestration for GLPI AI Gateway.

Creates and runs CrewAI crew with IT Support Agent to handle user queries.

CHANGELOG (bug-fix):
  - _format_history(): now correctly excludes only the *last* user message
    (the current question) instead of any message with matching content —
    fixing cases where the same question appears multiple times in history.
  - Task description: user context (user_id, session info) is now embedded
    in the history block header so it survives across tool calls.
  - Added explicit "Informasi Konteks Sesi" block so agent always knows
    the user_id even when restored from session (not in request body).
"""

import logging
from typing import Any

from crewai import Crew, LLM, Task, Process

from app.agents import build_it_support
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum number of previous messages to include as context.
_HISTORY_WINDOW = 10  # 5 turns = 10 messages (user + assistant)

_TOOL_ROUTING = """
PANDUAN PEMILIHAN TOOL (WAJIB IKUTI):
┌─────────────────────────────────────────────────────────────────────┐
│ Pertanyaan User               → Tool yang HARUS dipanggil           │
├─────────────────────────────────────────────────────────────────────┤
│ komputer/laptop/aset saya     → get_assets_by_user (user_id=X)      │
│ semua komputer / inventaris   → list_all_computers                  │
│ detail komputer ID X          → get_computer_detail (computer_id=X) │
│ kontrak / contract / vendor   → list_all_contracts                  │
│ kontrak aktif                 → list_all_contracts (active_only=True)│
│ detail kontrak ID X           → get_contract_detail (contract_id=X) │
│ tiket / request saya          → get_user_tickets (user_id=X)        │
│ profil / info akun            → get_user_profile (user_id=X)        │
│ supplier / vendor             → list_suppliers                      │
│ kategori tiket / ITIL         → list_itil_categories                │
│ cara / prosedur / panduan     → search_knowledge_base               │
└─────────────────────────────────────────────────────────────────────┘

LARANGAN MUTLAK:
• DILARANG menjawab pertanyaan tentang data GLPI tanpa memanggil tool
• DILARANG mengarang angka, nama, atau status yang tidak ada di output tool
• DILARANG menampilkan JSON, 'Action:', 'Thought:', atau format internal
"""


def _create_llm() -> LLM:
    """Initialize LLM for CrewAI using LiteLLM wrapper."""
    return LLM(
        model=f"openai/{settings.nemotron_model}",
        api_key=settings.ai_gateway_api_key,
        api_base=settings.resolved_ai_gateway_base_url,
        temperature=0.1,
    )


def _format_history(messages: list[dict[str, str]], current_message: str) -> str:
    """Format previous conversation turns into a readable context block.

    BUG FIX (v2.1): Previously used content-equality to exclude the current
    message, which silently dropped earlier occurrences of the same question.
    Now we exclude only the *last* user message by index, which is always the
    current question regardless of whether the same text appeared before.

    Args:
        messages       : Full merged messages array (already includes current turn).
        current_message: The latest user message text (used only as a label).

    Returns:
        Formatted string of prior turns, or empty string if none.
    """
    if not messages:
        return ""

    # Find index of the last user message (the current question).
    last_user_idx: int = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    # Prior messages = everything before the last user message
    prior = messages[:last_user_idx] if last_user_idx > 0 else []

    # Keep only the last N messages to avoid oversized prompts
    windowed = prior[-_HISTORY_WINDOW:]

    if not windowed:
        return ""

    lines: list[str] = []
    for msg in windowed:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Asisten: {content}")

    return "\n".join(lines)


def run_crew(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
) -> str:
    """Execute CrewAI crew to process user query about GLPI data.

    Args:
        user_message  : Latest user query to process.
        glpi_user_id  : GLPI user ID (0 for general queries without user context).
        messages      : Full merged conversation history (includes current turn).

    Returns:
        Final answer string from the agent.

    Note:
        This is a blocking call — use run_in_executor when calling from async context.
    """
    llm: LLM = _create_llm()
    agent: Any = build_it_support(llm, glpi_user_id=glpi_user_id)

    all_messages = messages or []
    history_text: str = _format_history(all_messages, user_message)

    # Build a rich context block for the task.
    # 1) Session context (always shown so agent knows who the user is)
    user_context_block = (
        f"[KONTEKS SESI]\n"
        f"• GLPI User ID aktif : {glpi_user_id if glpi_user_id > 0 else '(belum diketahui)'}\n"
        f"• Jumlah pesan dalam riwayat: {len(all_messages)}\n\n"
    )

    # 2) Conversation history (prior turns only, not the current question)
    history_block: str = (
        f"[RIWAYAT PERCAKAPAN SEBELUMNYA]\n{history_text}\n\n"
        if history_text
        else ""
    )

    task: Task = Task(
        description=f"""
{user_context_block}{history_block}[PERTANYAAN TERBARU DARI USER]
"{user_message}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATURAN PENGGUNAAN TOOL:

1. Jika pertanyaan merujuk JELAS pada data yang SUDAH ADA di riwayat percakapan
   di atas (contoh: "sebutkan komputer tersebut", "komputer yang tadi", "tiket itu"),
   JANGAN panggil tool lagi — gunakan langsung data dari riwayat percakapan.

2. Jika butuh data BARU dari GLPI:
   • Panduan/KB          → search_knowledge_base
   • Semua komputer      → get_all_computers
   • Aset milik user     → get_user_assets (user_id={glpi_user_id})
   • Tiket user          → get_user_tickets (user_id={glpi_user_id})
   • Profil user         → get_user_info (user_id={glpi_user_id})
   • Kontrak             → list_all_contracts
   • Supplier            → list_suppliers
   • Kategori ITIL       → list_itil_categories

3. SELALU gunakan user_id={glpi_user_id} untuk semua tool yang membutuhkan user_id.
   JANGAN gunakan user_id=0 jika user_id sudah diketahui.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Jawab dalam bahasa Indonesia yang sopan dan natural.
Jangan tampilkan format internal/JSON/Action/Thought.
        """,
        expected_output="Jawaban akhir dalam bahasa Indonesia.",
        agent=agent,
    )

    crew: Crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    prior_turns = len([m for m in all_messages if m.get("role") == "user"])
    logger.info(
        "Crew kickoff | user_id=%s | prior_turns=%d | msg='%s...'",
        glpi_user_id,
        max(0, prior_turns - 1),  # exclude current question
        user_message[:50],
    )

    try:
        result: Any = crew.kickoff()
        logger.info(
            "Crew done | user_id=%s | result='%s...'",
            glpi_user_id,
            str(result)[:100],
        )
        return str(result)
    except Exception as exc:
        logger.error("Crew execution failed: %s", exc)
        return "Mohon maaf, sistem sedang mengalami kendala internal."