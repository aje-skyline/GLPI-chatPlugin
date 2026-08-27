"""app/agents/agent_factory.py — LLM Singleton & Agent Factory.

Satu-satunya tempat di mana LLM di-inisialisasi dan Agent IT Support dibangun.
Konsumer (crew_orchestrator.py) cukup memanggil _get_agent() — tidak perlu
tahu detail konfigurasi LLM maupun toolset.

TANGGUNG JAWAB FILE INI:
  1. Menginisialisasi singleton LLM dari app.config.settings.
  2. Menginisialisasi singleton Agent dengan toolset lengkap dari app.tools.
  3. Mengekspos build_it_support() sebagai factory publik untuk testing/override.

SINGLETON PATTERN (double-checked locking):
  LLM dan Agent di-cache sebagai process-level singleton.
  - Menghilangkan overhead re-inisialisasi ~200-500ms per request.
  - Thread-safe: kedua lock digunakan untuk cold-start saja; hot-path
    (request ke-2 dst.) langsung return tanpa acquire lock.
  - LLM bersifat stateless terhadap conversation history (state percakapan
    disimpan di task description, bukan di object LLM), sehingga sharing
    instance antar request aman.

CHANGELOG:
  v1.0 — Dipecah dari crew_services.py (Tahap 4 Clean Architecture).
          Memindahkan _get_llm(), _get_agent(), _ROLE, _GOAL, _BACKSTORY,
          _TOOLS, dan build_it_support() dari crew_services.py / it_support.py.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from crewai import Agent, LLM

from app.config import settings
from app.tools import (
    tool_count_all_assets,
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

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Agent Identity Constants
# ══════════════════════════════════════════════════════════════════════════════

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
7. ATURAN DATA BESAR — WAJIB: Jika output tool berisi "[INSTRUKSI SISTEM]" → TULIS Final Answer LANGSUNG. \
DILARANG keras memanggil tool apapun lagi. Sebut totalcount exact dan tampilkan sampel yang ada. \
PENTING: Teks "[INSTRUKSI SISTEM]" dan poin-poin instruksinya adalah panduan internal untukmu — \
DILARANG KERAS menyalin atau menampilkan teks instruksi tersebut di dalam Final Answer.

PERINGATAN: Jika kamu mendapati diri menulis "Thought:" atau "Action:" di Final Answer \
— itu SALAH TOTAL. Panggil tool secara nyata, tunggu hasilnya, baru tulis Final Answer.
"""

# ── Toolset lengkap yang diberikan ke agent ────────────────────────────────────
# Urutan tidak mempengaruhi routing — CrewAI/LLM memilih tool berdasarkan
# name + description saat reasoning. Dikelompokkan per domain untuk keterbacaan.
_TOOLS: list[Any] = [
    # Knowledge Base
    tool_search_kb,
    # Computer — listing & counting
    tool_get_assets,
    tool_get_all_computers,
    tool_get_computer_detail,
    tool_count_all_assets,
    tool_count_all_computers,
    # Computer — searching
    tool_search_computer_by_name,
    tool_search_computer,
    # Computer — filtered by attribute
    tool_get_computers_by_status,
    tool_get_computers_by_location,
    tool_get_computers_by_os,
    # Supplier
    tool_get_suppliers,
    tool_count_suppliers,
    # Contracts
    tool_get_contracts,
    tool_get_contract_detail,
    # Tickets & User
    tool_get_tickets,
    tool_get_user_info,
    # Categories & Utilities
    tool_get_categories,
    tool_get_multiple_items,
    tool_list_search_options,
]


# ══════════════════════════════════════════════════════════════════════════════
# LLM Singleton
# ══════════════════════════════════════════════════════════════════════════════

_llm_instance: LLM | None = None
_llm_lock = threading.Lock()


def _get_llm() -> LLM:
    """Return singleton LLM instance, membuat satu kali jika belum ada.

    Menggunakan double-checked locking untuk thread safety tanpa overhead
    lock di setiap request setelah instance tersedia.

    Konfigurasi (Anti-TokenExplosion):
      max_tokens=2500
        Hard ceiling output LLM per satu completion call. Anatomy token budget
        per satu LLM call yang realistis:
          Thought singkat (~150 token) + Action+Input (~50 token) +
          Final Answer (~400 token) + buffer safety (~600 token) = ~1200 token.
        2500 = headroom ~2× di atas kebutuhan nyata, masih jauh di bawah
        batas token explosion (7000+).

      temperature=1
        Dipertahankan sesuai config lama. Verbositas dikontrol dari tool output
        ([INSTRUKSI SISTEM]) dan task description ([ATURAN THOUGHT]), bukan
        dari temperature rendah.
    """
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    with _llm_lock:
        if _llm_instance is None:
            _llm_instance = LLM(
                model=f"openai/{settings.ai_model}",
                api_key=settings.ai_gateway_api_key,
                api_base=settings.resolved_ai_gateway_base_url,
                temperature=0.0,
                max_tokens=4096,
            )
            logger.info(
                "LLM singleton created (model=%s, temperature=0.0, max_tokens=4096)",
                settings.ai_model,
            )
    return _llm_instance


# ══════════════════════════════════════════════════════════════════════════════
# Agent Singleton
# ══════════════════════════════════════════════════════════════════════════════

_agent_instance: Any | None = None
_agent_lock = threading.Lock()


def _get_agent() -> Any:
    """Return singleton Agent instance, membuat satu kali jika belum ada.

    Agent di-share antar request karena:
    1. Tools bersifat stateless (tidak menyimpan state request).
    2. Context percakapan disuntikkan via task description per-request,
       bukan disimpan di dalam object Agent.
    3. Menghilangkan overhead build_it_support() (load tools, schema
       validation Pydantic) yang memakan ~200-500ms per request.

    Diakses oleh crew_orchestrator.py untuk kedua entrypoint:
    run_crew() dan run_crew_async().
    """
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance
    with _agent_lock:
        if _agent_instance is None:
            _agent_instance = build_it_support(_get_llm(), glpi_user_id=0)
            logger.info("Agent singleton created")
    return _agent_instance


# ══════════════════════════════════════════════════════════════════════════════
# Public Factory
# ══════════════════════════════════════════════════════════════════════════════

def build_it_support(llm: LLM, glpi_user_id: int = 0) -> Agent:  # noqa: ARG001
    """Bangun IT Support Agent dengan toolset lengkap.

    Digunakan oleh _get_agent() untuk cold-start singleton, dan bisa dipanggil
    langsung dalam test untuk mendapatkan agent fresh dengan LLM mock.

    Args:
        llm          : Instance CrewAI LLM yang sudah dikonfigurasi.
                       Dibuat via _get_llm() agar inisialisasi terpusat.
        glpi_user_id : GLPI User ID aktif (0 = tidak diketahui).
                       Disimpan untuk future use (mis. tool-level filtering).
                       Parameter ini sengaja tidak digunakan langsung di sini
                       (noqa ARG001) — user_id disuntikkan via task description
                       oleh prompt_builder.py per-request.

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
        # max_iter=5: Turun dari 8 → 5.
        # Query sederhana (count/search) selesai 2 iter: tool call + Final Answer.
        # Query kompleks (search → detail → compare) butuh maks 3-4 iter.
        # 5 = safety net cukup tanpa risiko loop panjang.
        max_iter=5,
        max_retry_limit=2,
        # max_execution_time=55: Hard-stop 55s < server timeout 80s (main.py).
        # Memberi buffer 25s untuk cleanup SSE + sentinel queue.
        # CrewAI raise exception saat limit tercapai → ditangkap di crew_orchestrator.py.
        max_execution_time=55,
    )