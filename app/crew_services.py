"""CrewAI orchestration — GLPI AI Gateway.

Satu-satunya tempat inisialisasi LLM (CrewAI native) dan eksekusi Crew.
Semua konfigurasi LLM berasal dari `app.config.settings`.

CHANGELOG:
  v5.1 — Tambah _SUPPLIER_TOOL_GUIDANCE; routing count_suppliers.
  v4.0 — Smart Pagination & Large Data Handling.
  v3.0 — Task description ringkas; sanitize_agent_output post-processing.
"""

import logging
from typing import Any

from crewai import Crew, LLM, Process, Task

from app.agents import build_it_support
from app.config import settings
from app.utils import sanitize_agent_output

logger = logging.getLogger(__name__)

# Jumlah pesan sebelumnya yang disertakan sebagai konteks (5 turns = 10 messages).
_HISTORY_WINDOW: int = 10


# ── LLM Factory ───────────────────────────────────────────────────────────────

def _create_llm() -> LLM:
    """Inisialisasi CrewAI LLM native untuk AI Gateway kustom.

    Menggunakan prefix "openai/" pada nama model karena AI Gateway
    yang dipakai kompatibel dengan OpenAI API spec. CrewAI meneruskan
    prefix ini ke LiteLLM internal-nya untuk pemilihan provider yang tepat.

    Tidak ada import `litellm` atau `langchain` di sini — semuanya
    ditangani oleh CrewAI secara internal.

    Returns:
        Instance `crewai.LLM` yang siap digunakan oleh Agent.
    """
    return LLM(
        model=f"openai/{settings.ai_model}",   # prefix "openai/" = OpenAI-compatible gateway
        api_key=settings.ai_gateway_api_key,
        api_base=settings.resolved_ai_gateway_base_url,
        temperature=1,
    )


# ── Task Guidance Strings ─────────────────────────────────────────────────────

_LARGE_DATA_GUIDANCE: str = """\
[PANDUAN INTERPRETASI HASIL TOOL — DATA BESAR]

Tools inventaris komputer (get_all_computers, get_computers_by_*) mengembalikan
output dalam format SMART PAGINATION:

  ✅ Total: X.XXX komputer ditemukan di GLPI.
  ⚠️  Data terlalu besar — menampilkan YY sampel pertama.
  📊 Statistik Distribusi: Status / Lokasi / OS
  [baris-baris data sampel]
  📌 ... dan ZZZ item lainnya tidak ditampilkan.

ATURAN WAJIB:
1. "Total: X.XXX" = JUMLAH EXACT dari database — gunakan ini untuk pertanyaan count.
2. Flag ⚠️ = data ditampilkan hanyalah SAMPLE — sampaikan ke user.
3. Untuk count by filter → get_computers_by_location / get_computers_by_status.
4. JANGAN panggil get_all_computers hanya untuk count → gunakan count_all_computers.
"""

_SUPPLIER_TOOL_GUIDANCE: str = """\
[PANDUAN PENGGUNAAN TOOL SUPPLIER]

Tersedia DUA tool supplier — pilih yang tepat:

  A) count_suppliers  → HANYA menghitung jumlah total (1 API call, cepat)
     Gunakan untuk: "ada berapa supplier?", "total vendor?", pertanyaan COUNT.
     JANGAN gunakan get_suppliers(limit=besar) hanya untuk count.

  B) get_suppliers    → List/cari supplier dengan detail lengkap
     Parameter filter (semua opsional, dikombinasi AND):
       name / entity / address / phone / fax / email / limit (default 50, maks 500)

PEMETAAN INTENT → TOOL:
  "ada berapa total supplier?"           → count_suppliers()
  "berikan detail supplier SYNNEX"       → get_suppliers(name="SYNNEX")
  "supplier yang alamatnya di Jakarta"   → get_suppliers(address="Jakarta")
  "daftar semua supplier"                → get_suppliers()

ATURAN:
1. COUNT → count_suppliers. JANGAN get_suppliers dengan limit besar.
2. DETAIL/LIST → get_suppliers dengan filter relevan.
3. limit > 50 hanya jika user eksplisit meminta semua data.
"""


# ── History Formatter ─────────────────────────────────────────────────────────

def _format_history(messages: list[dict[str, str]], current_message: str) -> str:
    """Format riwayat percakapan sebelumnya menjadi blok konteks terbaca.

    Mengecualikan pesan user terakhir (pertanyaan saat ini).

    Args:
        messages       : Array pesan lengkap termasuk turn saat ini.
        current_message: Teks pesan user terbaru (hanya untuk referensi log).

    Returns:
        String riwayat terformat, atau string kosong jika tidak ada.
    """
    if not messages:
        return ""

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


# ── Task Description Builder ──────────────────────────────────────────────────

def _build_task_description(
    user_message: str,
    glpi_user_id: int,
    all_messages: list[dict[str, str]],
) -> str:
    """Bangun task description lengkap untuk satu request."""
    history_text = _format_history(all_messages, user_message)

    uid_label = (
        f"user_id={glpi_user_id}"
        if glpi_user_id > 0
        else "user_id=UNKNOWN (jangan panggil tool personal tanpa ID yang valid)"
    )

    user_context_block = (
        "[KONTEKS SESI]\n"
        f"• GLPI User ID aktif : "
        f"{glpi_user_id if glpi_user_id > 0 else '(belum diketahui)'}\n"
        f"• Jumlah pesan dalam riwayat: {len(all_messages)}\n\n"
    )

    history_block = (
        f"[RIWAYAT PERCAKAPAN SEBELUMNYA]\n{history_text}\n\n"
        if history_text
        else ""
    )

    return f"""\
{user_context_block}{history_block}\
[PERTANYAAN TERBARU DARI USER]
"{user_message}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PANDUAN PENGERJAAN:

1. Periksa riwayat di atas. Jika data sudah ada dan user merujuknya
   ("komputer tadi", "tiket itu") → JANGAN panggil tool lagi.

2. Jika data belum ada, pilih tool yang sesuai:
   • Jumlah/total komputer      → count_all_computers
   • Jumlah/total supplier      → count_suppliers
   • Panduan/KB                 → search_knowledge_base
   • Semua komputer + statistik → get_all_computers
   • Cari komputer              → search_computer
   • Komputer by lokasi         → get_computers_by_location
   • Komputer by status         → get_computers_by_status
   • Komputer by OS             → get_computers_by_os
   • Aset milik user            → get_user_assets ({uid_label})
   • Detail komputer by ID      → get_computer_detail
   • Tiket user                 → get_user_tickets ({uid_label})
   • Profil user                → get_user_info ({uid_label})
   • Kontrak                    → list_all_contracts
   • Detail kontrak by ID       → get_contract_detail
   • Supplier list/detail/cari  → get_suppliers  (lihat panduan bawah)
   • Kategori ITIL              → get_itil_categories

3. WAJIB: Semua tool yang butuh user_id → gunakan {uid_label}.

{_LARGE_DATA_GUIDANCE}

{_SUPPLIER_TOOL_GUIDANCE}

4. Tulis Final Answer dalam Bahasa Indonesia yang sopan dan natural.
   JANGAN tampilkan JSON, "Action:", "Thought:", atau format internal apapun.
   Gunakan angka dari output tool — JANGAN tebak-tebak.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


# ── Public API ────────────────────────────────────────────────────────────────

def run_crew(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
) -> str:
    """Jalankan CrewAI Crew untuk memproses satu query user GLPI.

    Ini adalah blocking call — panggil via `loop.run_in_executor` dari
    konteks async (sudah dilakukan di main.py).

    Args:
        user_message  : Query user terbaru.
        glpi_user_id  : GLPI User ID (0 untuk query umum).
        messages      : Riwayat percakapan lengkap termasuk turn saat ini.

    Returns:
        Jawaban final yang sudah di-sanitize, siap ditampilkan ke user.
    """
    all_messages: list[dict[str, str]] = messages or []

    # LLM dibuat fresh per request agar tidak ada state tersisa antar sesi.
    llm: LLM = _create_llm()
    agent: Any = build_it_support(llm, glpi_user_id=glpi_user_id)

    task: Task = Task(
        description=_build_task_description(user_message, glpi_user_id, all_messages),
        expected_output=(
            "Jawaban akhir dalam Bahasa Indonesia yang sopan, akurat berdasarkan "
            "data dari tool, tanpa format internal seperti Thought/Action/JSON. "
            "Untuk inventaris besar: sebutkan jumlah exact dari totalcount tool. "
            "Untuk supplier: tampilkan Name, Entity, Alamat, Telepon, Fax, Email."
        ),
        agent=agent,
    )

    crew: Crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=settings.crew_verbose,
    )

    prior_turns = max(0, len([m for m in all_messages if m.get("role") == "user"]) - 1)
    logger.info(
        "Crew kickoff | user_id=%s | prior_turns=%d | msg='%.80s'",
        glpi_user_id,
        prior_turns,
        user_message,
    )

    try:
        result: Any = crew.kickoff()
        clean_str = sanitize_agent_output(str(result))

        logger.info(
            "Crew done | user_id=%s | result='%.120s'",
            glpi_user_id,
            clean_str,
        )
        return clean_str

    except Exception as exc:
        logger.error("Crew execution failed: %s", exc, exc_info=True)
        return "Mohon maaf, sistem sedang mengalami kendala teknis. Silakan coba beberapa saat lagi."