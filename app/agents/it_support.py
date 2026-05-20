"""IT Support Agent — GLPI AI Gateway.

Membangun CrewAI Agent dengan toolset lengkap untuk query data GLPI.
LLM diterima sebagai parameter dari crew_services.py sehingga inisialisasi
terpusat di satu tempat dan agent ini tetap stateless & testable.

CHANGELOG:
  v5.1 — Tambah tool_count_suppliers.
  v3.0 — Backstory rewrite: anti-hallucination, larangan Thought/Action di output.
"""

from typing import Any

from crewai import Agent, LLM

from app.config import settings
from app.tools import (
    tool_count_all_computers,
    tool_count_suppliers,
    tool_get_all_computers,
    tool_get_assets,
    tool_get_categories,
    tool_get_computer_detail,
    tool_get_computers_by_location,
    tool_get_computers_by_os,
    tool_get_computers_by_status,
    tool_get_contract_detail,
    tool_get_contracts,
    tool_get_multiple_items,
    tool_get_suppliers,
    tool_get_tickets,
    tool_get_user_info,
    tool_list_search_options,
    tool_search_computer,
    tool_search_computer_by_name,
    tool_search_kb,
)

# ── Agent Identity ─────────────────────────────────────────────────────────────

_ROLE: str = "IT Support Specialist GLPI"

_GOAL: str = (
    "Jawab pertanyaan user tentang data GLPI (aset, tiket, kontrak, KB, dll) "
    "secara akurat menggunakan HANYA data dari tool. "
    "JANGAN mengarang, mengasumsikan, atau menjawab dari memori sendiri."
)

_BACKSTORY: str = """\
Kamu adalah IT Support Specialist yang mengelola sistem GLPI dan menjawab \
pertanyaan tentang aset IT, tiket, kontrak, dan panduan.

ATURAN WAJIB:
1. SELALU panggil tool sebelum menjawab data apa pun — DILARANG menjawab dari memori.
2. Jawaban = output tool 100%. Tool → 3 item → sebut 3 item itu. Tool → 0 → "tidak ditemukan".
3. Pilih tool yang tepat (lihat panduan di task description).
4. Final Answer hanya berisi teks Bahasa Indonesia yang sopan dan natural — \
DILARANG menulis "Thought:", "Action:", "Action Input:", "Observation:", JSON mentah, \
atau proses berpikir internal.
5. Jika data SUDAH ADA di riwayat percakapan dan user merujuknya ("komputer tadi", \
"tiket itu") → gunakan data riwayat, JANGAN panggil tool lagi.
6. Jika user_id=0 dan user bertanya data milik sendiri → sampaikan sistem belum \
mendeteksi identitas, minta hubungi admin IT.

PERINGATAN: Jika kamu mendapati diri menulis "Thought:" atau "Action:" di Final Answer \
— itu SALAH TOTAL. Panggil tool secara nyata, tunggu hasilnya, baru tulis Final Answer.
"""

# ── Toolset ────────────────────────────────────────────────────────────────────

_TOOLS: list[Any] = [
    tool_search_kb,
    tool_get_assets,
    tool_get_all_computers,
    tool_get_computer_detail,
    tool_get_contracts,
    tool_get_contract_detail,
    tool_get_multiple_items,
    tool_list_search_options,
    tool_get_tickets,
    tool_get_user_info,
    tool_get_categories,
    tool_get_suppliers,
    tool_count_suppliers,
    tool_count_all_computers,
    tool_search_computer_by_name,
    tool_search_computer,
    tool_get_computers_by_status,
    tool_get_computers_by_location,
    tool_get_computers_by_os,
]


def build_it_support(llm: LLM, glpi_user_id: int = 0) -> Agent:  # noqa: ARG001
    """Bangun IT Support Agent dengan toolset lengkap.

    Args:
        llm          : Instance CrewAI LLM yang sudah dikonfigurasi.
                       Dibuat di crew_services.py agar inisialisasi terpusat.
        glpi_user_id : GLPI User ID aktif (0 = tidak diketahui).
                       Disimpan untuk future use (mis. tool-level filtering).

    Returns:
        Agent CrewAI yang siap dimasukkan ke dalam Crew.
    """
    return Agent(
        role=_ROLE,
        goal=_GOAL,
        backstory=_BACKSTORY,
        tools=_TOOLS,
        llm=llm,
        verbose=settings.crew_verbose,
        allow_delegation=False,
        max_iter=15,
        max_retry_limit=2,
    )