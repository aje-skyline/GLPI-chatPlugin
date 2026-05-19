"""CrewAI orchestration untuk GLPI AI Gateway.

Membuat dan menjalankan CrewAI crew dengan IT Support Agent untuk menangani
query user tentang data GLPI.

CHANGELOG v4.0 — Smart Pagination & Large Data Handling:
  - Task description diperbarui: instruksi eksplisit tentang cara LLM harus
    menafsirkan output tools yang berisi totalcount dan summary stats.
  - Tambah seksi "INTERPRETASI DATA BESAR" di task: agent diarahkan untuk
    menggunakan totalcount exact dari tool, bukan mencoba menghitung baris.
  - _LARGE_DATA_GUIDANCE: konstanta terpisah agar mudah di-tune.
  - Tidak ada perubahan di _format_history atau run_crew — logika bisnis sama.

CHANGELOG v3.0:
  - Task description: lebih ringkas, hindari ambiguitas.
  - Tambah post-processing agresif via sanitize_agent_output.
"""

import logging
import re
from typing import Any

from crewai import Crew, LLM, Task, Process

from app.agents import build_it_support
from app.config import settings
from app.utils import sanitize_agent_output

logger = logging.getLogger(__name__)

# Jumlah pesan sebelumnya yang disertakan sebagai konteks.
_HISTORY_WINDOW = 10  # 5 turns = 10 messages (user + assistant)

# ── Panduan interpretasi data besar — disuntikkan ke task description ─────────
# Dipisah sebagai konstanta agar mudah di-tune tanpa mengubah logika utama.
_LARGE_DATA_GUIDANCE: str = """\
[PANDUAN INTERPRETASI HASIL TOOL — DATA BESAR]

Tools inventaris komputer (get_all_computers, get_computers_by_*) sekarang
mengembalikan output dalam format SMART PAGINATION:

  ✅ Total: X.XXX komputer ditemukan di GLPI.
  ⚠️  Data terlalu besar — menampilkan YY sampel pertama. ...
  📊 Statistik Distribusi:
     Status: ...
     Lokasi: ...
     OS: ...
  [baris-baris data sampel]
  📌 ... dan ZZZ item lainnya tidak ditampilkan.

ATURAN WAJIB saat membaca output tools:
1. Angka "Total: X.XXX" adalah JUMLAH EXACT dari database GLPI — gunakan angka
   ini saat user bertanya "ada berapa" atau "jumlah total". JANGAN hitung baris.
2. Jika ada flag ⚠️ (truncated), sampaikan ke user bahwa data yang ditampilkan
   hanyalah SAMPLE — total sesungguhnya ada di baris "Total: ...".
3. Statistik distribusi (📊) adalah ringkasan dari sample yang ada. Jika ada
   flag truncated, sampaikan bahwa statistik berdasarkan sample, bukan keseluruhan.
4. Untuk pertanyaan jumlah by filter (mis: "berapa komputer di Lantai 3"),
   gunakan tool get_computers_by_location atau get_computers_by_status —
   totalcount dari tool tersebut adalah jumlah exact untuk filter itu.
5. JANGAN panggil get_all_computers hanya untuk mendapat jumlah total —
   gunakan count_all_computers yang lebih cepat (1 API call, bukan paginasi).
"""


def _create_llm() -> LLM:
    """Inisialisasi LLM untuk CrewAI menggunakan LiteLLM wrapper."""
    return LLM(
        model=f"openai/{settings.ai_model}",
        api_key=settings.ai_gateway_api_key,
        api_base=settings.resolved_ai_gateway_base_url,
        temperature=1,
    )


def _format_history(messages: list[dict[str, str]], current_message: str) -> str:
    """Format turn percakapan sebelumnya menjadi blok konteks yang dapat dibaca.

    Mengecualikan pesan user terakhir (pertanyaan saat ini) berdasarkan index.

    Args:
        messages       : Array pesan lengkap (termasuk turn saat ini).
        current_message: Teks pesan user terbaru (digunakan hanya sebagai label).

    Returns:
        String turn sebelumnya yang terformat, atau empty string jika tidak ada.
    """
    if not messages:
        return ""

    # Cari index pesan user terakhir (pertanyaan saat ini).
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
        role    = msg.get("role", "")
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
    """Jalankan CrewAI crew untuk memproses query user tentang data GLPI.

    Args:
        user_message  : Query user terbaru.
        glpi_user_id  : GLPI User ID (0 untuk query umum tanpa konteks user).
        messages      : Riwayat percakapan lengkap (termasuk turn saat ini).

    Returns:
        Jawaban akhir dari agent (sudah dipost-process).

    Note:
        Ini adalah blocking call — gunakan run_in_executor saat dipanggil
        dari konteks async.
    """
    llm: LLM = _create_llm()
    agent: Any = build_it_support(llm, glpi_user_id=glpi_user_id)

    all_messages = messages or []
    history_text: str = _format_history(all_messages, user_message)

    # ── Blok 1: Konteks sesi ──────────────────────────────────────────────────
    user_context_block = (
        "[KONTEKS SESI]\n"
        f"• GLPI User ID aktif : "
        f"{glpi_user_id if glpi_user_id > 0 else '(belum diketahui — jangan gunakan user_id=0 untuk query personal)'}\n"
        f"• Jumlah pesan dalam riwayat: {len(all_messages)}\n\n"
    )

    # ── Blok 2: Riwayat percakapan ────────────────────────────────────────────
    history_block: str = (
        f"[RIWAYAT PERCAKAPAN SEBELUMNYA]\n{history_text}\n\n"
        if history_text
        else ""
    )

    # ── Blok 3: Tool routing berdasarkan user_id ──────────────────────────────
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
   • Jumlah/total komputer (HANYA COUNT)  → count_all_computers
   • Panduan/KB                           → search_knowledge_base
   • Semua komputer + total + statistik   → get_all_computers
   • Cari komputer (nama/serial/inv)      → search_computer
   • Komputer by lokasi + total           → get_computers_by_location
   • Komputer by status + total           → get_computers_by_status
   • Komputer by OS + total               → get_computers_by_os
   • Aset milik user                      → get_user_assets ({uid_note})
   • Detail komputer by ID                → get_computer_detail
   • Tiket user                           → get_user_tickets ({uid_note})
   • Profil user                          → get_user_info ({uid_note})
   • Kontrak                              → list_all_contracts
   • Detail kontrak by ID                 → get_contract_detail
   • Supplier                             → get_suppliers
   • Kategori ITIL                        → get_itil_categories

3. WAJIB: Semua tool yang butuh user_id → gunakan {uid_note}.

{_LARGE_DATA_GUIDANCE}

4. Tulis Final Answer dalam Bahasa Indonesia yang sopan dan natural.
   JANGAN tampilkan JSON, "Action:", "Thought:", atau format internal apapun.
   Saat menyebut jumlah komputer, gunakan angka dari "Total:" di output tool —
   JANGAN menghitung baris atau menebak-nebak.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\
"""

    task: Task = Task(
        description=task_description,
        expected_output=(
            "Jawaban akhir dalam Bahasa Indonesia yang sopan, akurat berdasarkan "
            "data dari tool, tanpa format internal seperti Thought/Action/JSON. "
            "Untuk data inventaris besar: sebutkan jumlah exact dari totalcount tool, "
            "rangkum statistik distribusi jika tersedia, dan berikan beberapa contoh "
            "item sebagai ilustrasi — tidak perlu sebutkan semua baris."
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