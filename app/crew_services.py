"""CrewAI orchestration for GLPI AI Gateway.

Creates and runs CrewAI crew with IT Support Agent to handle user queries.

FIXES v3.0:
  - Task description: lebih ringkas, hindari ambiguitas yang membuat agent
    bingung antara "pakai riwayat" vs "panggil tool".
  - Tambah post-processing agresif: buang semua sisa Thought/Action yang
    bocor ke output sebelum dikembalikan ke user.
  - _format_history: tetap pakai pendekatan v2.1 (exclude last user by index).
  - _postprocess_result: fungsi baru yang lebih robust untuk membersihkan
    output agent.
  - Hapus _TOOL_ROUTING dari sini (sudah dipindah ke backstory agent).
"""

import logging
import re
from typing import Any

from crewai import Crew, LLM, Task, Process

from app.agents import build_it_support
from app.config import settings
from app.utils import sanitize_agent_output  # FIX #2: shared canonical sanitizer

logger = logging.getLogger(__name__)

# Maximum number of previous messages to include as context.
_HISTORY_WINDOW = 10  # 5 turns = 10 messages (user + assistant)


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

    Excludes only the *last* user message by index (the current question).

    Args:
        messages       : Full merged messages array (includes current turn).
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

    prior = messages[:last_user_idx] if last_user_idx > 0 else []
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


# _postprocess_result removed — FIX #2: now using app.utils.sanitize_agent_output
# which is the single canonical implementation shared with main.py.


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
        Final answer string from the agent (already post-processed).

    Note:
        This is a blocking call — use run_in_executor when calling from async context.
    """
    llm: LLM = _create_llm()
    agent: Any = build_it_support(llm, glpi_user_id=glpi_user_id)

    all_messages = messages or []
    history_text: str = _format_history(all_messages, user_message)

    # ── Blok 1: Konteks sesi (selalu ditampilkan) ─────────────────────────────
    user_context_block = (
        "[KONTEKS SESI]\n"
        f"• GLPI User ID aktif : {glpi_user_id if glpi_user_id > 0 else '(belum diketahui — jangan gunakan user_id=0 untuk query personal)'}\n"
        f"• Jumlah pesan dalam riwayat: {len(all_messages)}\n\n"
    )

    # ── Blok 2: Riwayat percakapan (hanya turn sebelumnya) ───────────────────
    history_block: str = (
        f"[RIWAYAT PERCAKAPAN SEBELUMNYA]\n{history_text}\n\n"
        if history_text
        else ""
    )

    # ── Blok 3: Panduan tool berdasarkan user_id ─────────────────────────────
    uid_note = (
        f"user_id={glpi_user_id}"
        if glpi_user_id > 0
        else "user_id=UNKNOWN (jangan panggil tool personal tanpa ID yang valid)"
    )

    task_description = f"""\
{user_context_block}{history_block}\
[PERTANYAAN TERBARU DARI USER]
"{user_message}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PANDUAN PENGERJAAN:

1. Periksa riwayat percakapan di atas. Jika data yang diperlukan SUDAH ADA
   dan user hanya merujuk data itu (mis. "komputer tadi", "tiket itu"),
   JANGAN panggil tool lagi — gunakan data dari riwayat.

2. Jika data BELUM ADA atau user meminta data baru, panggil tool yang sesuai:
   • Panduan/KB             → search_knowledge_base
   • Semua komputer         → get_all_computers
   • Jumlah/total komputer  → count_all_computers
   • Cari komputer (nama/serial/inv) → search_computer
   • Komputer by lokasi     → get_computers_by_location
   • Komputer by status     → get_computers_by_status
   • Komputer by OS         → get_computers_by_os
   • Aset milik user        → get_user_assets ({uid_note})
   • Detail komputer by ID  → get_computer_detail
   • Tiket user             → get_user_tickets ({uid_note})
   • Profil user            → get_user_info ({uid_note})
   • Kontrak                → list_all_contracts
   • Detail kontrak by ID   → get_contract_detail
   • Supplier               → get_suppliers
   • Kategori ITIL          → get_itil_categories

3. WAJIB: Semua tool yang butuh user_id → gunakan {uid_note}.

4. Tulis Final Answer dalam Bahasa Indonesia yang sopan dan natural.
   JANGAN tampilkan JSON, "Action:", "Thought:", atau format internal apapun.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\
"""

    task: Task = Task(
        description=task_description,
        expected_output=(
            "Jawaban akhir dalam Bahasa Indonesia yang sopan, akurat berdasarkan "
            "data dari tool, tanpa format internal seperti Thought/Action/JSON."
        ),
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
        max(0, prior_turns - 1),
        user_message[:80],
    )

    try:
        result: Any = crew.kickoff()
        raw_str = str(result)

        # FIX #2: use shared canonical sanitizer instead of local _postprocess_result
        clean_str = sanitize_agent_output(raw_str)

        logger.info(
            "Crew done | user_id=%s | result='%s...'",
            glpi_user_id,
            clean_str[:120],
        )
        return clean_str

    except Exception as exc:
        logger.error("Crew execution failed: %s", exc, exc_info=True)
        return "Mohon maaf, sistem sedang mengalami kendala teknis. Silakan coba beberapa saat lagi."