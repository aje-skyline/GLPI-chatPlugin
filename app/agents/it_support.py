"""IT Support Agent definition for GLPI queries.

Agent uses BaseTool instances to fetch GLPI data (assets, tickets, contracts, etc.).
Anti-hallucination rules ensure data only comes from tools, never from memory.

FIXES v3.0:
  - Backstory rewritten: lebih konkret, kurangi ambiguitas, perkuat larangan
    menulis "Thought/Action" di Final Answer.
  - System prompt pakai format numerik yang lebih tegas dan lebih pendek.
  - Tambah penanganan edge-case "user_id=0" secara eksplisit.
  - Tool routing table dipadatkan agar tidak terlalu panjang (LLM cenderung
    mengabaikan bagian akhir prompt yang sangat panjang).
"""

from typing import Any

from crewai import Agent, LLM

from app.config import settings  # FIX #5: import settings at module level
from app.tools import (
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
    tool_count_all_computers,
    tool_search_computer_by_name,
    tool_search_computer,
    tool_get_computers_by_status,
    tool_get_computers_by_location,
    tool_get_computers_by_os,
)

# ── Agent Identity ────────────────────────────────────────────────────────────

ROLE: str = "IT Support Specialist GLPI"

GOAL: str = (
    "Jawab pertanyaan user tentang data GLPI (aset, tiket, kontrak, KB, dll) "
    "secara akurat menggunakan HANYA data dari tool. "
    "JANGAN mengarang, mengasumsikan, atau menjawab dari memori sendiri."
)

BACKSTORY: str = """\
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


def build_it_support(llm: LLM, glpi_user_id: int = 0) -> Agent:
    """Build the IT Support Agent with the appropriate toolset."""

    tools: list[Any] = [
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
        tool_count_all_computers,
        tool_search_computer_by_name,
        tool_search_computer,
        tool_get_computers_by_status,
        tool_get_computers_by_location,
        tool_get_computers_by_os,
    ]

    return Agent(
        role=ROLE,
        goal=GOAL,
        backstory=BACKSTORY,
        tools=tools,
        llm=llm,
        verbose=settings.crew_verbose,   # FIX #5: controlled via env, default False
        allow_delegation=False,
        max_iter=15,        # FIX #4: raised from 10 → 15 for multi-tool query chains
        max_retry_limit=2,
    )