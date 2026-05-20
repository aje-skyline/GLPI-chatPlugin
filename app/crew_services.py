"""CrewAI orchestration — GLPI AI Gateway.

Satu-satunya tempat inisialisasi LLM (CrewAI native) dan eksekusi Crew.
Semua konfigurasi LLM berasal dari `app.config.settings`.

CHANGELOG:
  v8.0 — True async streaming via kickoff_async() + step_callback + asyncio.Queue.
          Tambah run_crew_async() sebagai entry point utama untuk streaming SSE.
          run_crew() dipertahankan sebagai fallback untuk non-streaming path.
          _extract_step_text() untuk normalisasi berbagai tipe step_callback output.
  v7.1 — Fix "None or empty" crash: max_tokens naik 1500→2500.
  v7.0 — Anti-TokenExplosion: temperature=0.2; Crew verbose=True hardcode.
  v6.0 — Singleton LLM & Agent; _HISTORY_WINDOW 10 → 6.
  v5.1 — Tambah _SUPPLIER_TOOL_GUIDANCE; routing count_suppliers.
"""

import asyncio
import logging
import sys
import threading
from typing import Any

from crewai import Crew, LLM, Process, Task

from app.agents import build_it_support
from app.config import settings
from app.utils import sanitize_agent_output

logger = logging.getLogger(__name__)


# ── Guard: Pastikan stdout CrewAI (rich) tidak ditimpa uvicorn/FastAPI ────────
def _preserve_crewai_stdout() -> None:
    """Pastikan sys.stdout tidak pernah diganti dengan NullWriter-like object.

    CrewAI mencetak via rich.Console(stderr=False) yang membaca sys.stdout
    pada saat print. Jika uvicorn sudah me-redirect stdout, kembalikan ke
    sys.__stdout__ agar kotak ASCII rich tetap terlihat di terminal.
    """
    try:
        if not hasattr(sys.stdout, "fileno"):
            sys.stdout = sys.__stdout__
            return
        sys.stdout.fileno()
    except Exception:
        sys.stdout = sys.__stdout__


_preserve_crewai_stdout()

# Jumlah pesan sebelumnya yang disertakan sebagai konteks (2 turns = 4 messages).
# v8.0: Dikurangi dari 6 → 4. Setiap tambahan pesan memperbesar task description
# yang masuk ke setiap LLM call. Dengan supplier query berisi data tabel panjang
# di riwayat, lebih besar task = lebih tinggi risiko token explosion.
_HISTORY_WINDOW: int = 4


# ── LLM & Agent Singleton ─────────────────────────────────────────────────────
#
# LLM dan Agent di-cache sebagai singleton process-level.
# Ini menghilangkan overhead re-inisialisasi (schema validation, tool loading)
# yang terjadi di setiap request. Thread-safe via double-checked locking.
#
# CATATAN: LLM instance CrewAI bersifat stateless terhadap conversation history
# (state percakapan disimpan di task description, bukan di object LLM),
# sehingga sharing instance antar request aman dilakukan.

_llm_instance: LLM | None = None
_llm_lock = threading.Lock()

_agent_instance: Any | None = None
_agent_lock = threading.Lock()


def _get_llm() -> LLM:
    """Return singleton LLM instance, membuat satu kali jika belum ada.

    Menggunakan double-checked locking untuk thread safety tanpa overhead
    lock di setiap request setelah instance tersedia.

    Konfigurasi Anti-TokenExplosion (v7.1):
      - max_tokens=2500 : Hard ceiling output LLM per satu completion call.

        KENAPA 2500, bukan 1500 (percobaan v7.0)?
        Dengan prompt input ~3700 token, model masih menulis Thought panjang
        sebelum Action → mentok tepat di 1500 → output terpotong mid-JSON →
        CrewAI menerima respons None/empty → retry 3× → Crew gagal total.

        Anatomy token budget per satu LLM call yang realistis:
          Thought singkat (dikontrol [ATURAN THOUGHT]) :  ~150 token
          Action + Action Input (panggil tool)          :  ~50  token
          Final Answer (setelah tool result)            :  ~400 token
          Buffer safety 2×                              :  ~600 token
          ─────────────────────────────────────────────────────────
          Total realistis per call                      : ~1200 token
          → 2500 = headroom ~2× di atas kebutuhan nyata.
             Masih jauh di bawah batas token explosion (7000+).
             Verbositas dikontrol dari tool output ([INSTRUKSI SISTEM])
             dan task description ([ATURAN THOUGHT]), bukan dari max_tokens.

      - temperature=1
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
                # v8.0: temperature diturunkan dari 1 → 0.2.
                # Penjelasan: temperature tinggi membuat LLM "kreatif" —
                # lebih mungkin mengabaikan instruksi stop dan mencoba
                # cara lain untuk mendapatkan "semua data". temperature=0.2
                # membuat model lebih patuh dan deterministik terhadap
                # instruksi [INSTRUKSI SISTEM] di output tool.
                temperature=1,
                # max_tokens=2500 sudah didokumentasikan di docstring sejak v7.1
                # tapi tidak pernah di-set di kode. Fix ini memastikan LLM tidak
                # menghasilkan output > 2500 token per call — mencegah verbose
                # Thought panjang yang menghabiskan budget token sebelum Final Answer.
                max_tokens=2500,
            )
            logger.info(
                "LLM singleton created (model=%s, temperature=0.2, max_tokens=2500)",
                settings.ai_model,
            )
    return _llm_instance


def _get_agent() -> Any:
    """Return singleton Agent instance, membuat satu kali jika belum ada.

    Agent di-share antar request karena:
    1. Tools bersifat stateless (tidak menyimpan state request).
    2. Context percakapan disuntikkan via task description per-request,
       bukan disimpan di dalam object Agent.
    3. Menghilangkan overhead build_it_support() (load tools, schema
       validation Pydantic) yang memakan ~200-500ms per request.
    """
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance
    with _agent_lock:
        if _agent_instance is None:
            _agent_instance = build_it_support(_get_llm(), glpi_user_id=0)
            logger.info("Agent singleton created")
    return _agent_instance


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

_SUPPLIER_TOOL_GUIDANCE: str = """
[PANDUAN PENGGUNAAN TOOL SUPPLIER — WAJIB DIIKUTI]
Tersedia DUA tool supplier — pilih yang tepat:
A) count_suppliers  → HANYA menghitung jumlah total (1 API call, ~1 detik)
   Gunakan untuk: "ada berapa supplier?", "total vendor?", pertanyaan COUNT.
B) get_suppliers    → List/cari supplier dengan detail lengkap
   Parameter filter (semua opsional, dikombinasi AND):
   name / entity / address / phone / fax / email / limit (default 20, MAKS 20)

ATURAN WAJIB UNTUK "DAFTAR SEMUA" / "TAMPILKAN SEMUA SUPPLIER":
1. PANGGIL get_suppliers(limit=20) — SEKALI SAJA.
2. Tool mengembalikan totalcount exact + sampel ≤ 5 baris.
3. Setelah tool mengembalikan output dengan [INSTRUKSI SISTEM — WAJIB DIIKUTI]:
   → TULIS Final Answer LANGSUNG. JANGAN panggil tool apapun lagi.
   → JANGAN coba limit lebih besar, offset berbeda, atau filter tambahan
     hanya untuk mendapatkan "sisa" data.
4. Sampaikan ke user: "Terdapat X supplier terdaftar. Berikut contoh teratas.
   Sebutkan nama/kota/email spesifik jika ingin mencari supplier tertentu."

⛔ LARANGAN KERAS: Memanggil get_suppliers lebih dari SATU KALI per pertanyaan
   (kecuali filter berbeda karena user meminta supplier spesifik).
   Looping tool untuk pagination = TIMEOUT SISTEM → user tidak mendapat jawaban.

PEMETAAN INTENT → TOOL:
"ada berapa total supplier?"           → count_suppliers()
"daftar semua supplier"                → get_suppliers(limit=20) — SEKALI SAJA
"berikan detail supplier SYNNEX"       → get_suppliers(name="SYNNEX")
"supplier yang alamatnya di Jakarta"   → get_suppliers(address="Jakarta")
"berapa supplier + daftarnya"          → count_suppliers() LALU get_suppliers(limit=20)
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

    # Batas karakter per pesan asisten di history.
    # Mencegah tabel data panjang (supplier, komputer) membengkakkan task description
    # di setiap turn berikutnya. User message TIDAK dipotong.
    _MAX_ASSISTANT_CONTENT: int = 400

    lines: list[str] = []
    for msg in windowed:
        role    = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            # Potong jawaban panjang — cukup 400 karakter untuk memberi konteks
            # ke agent bahwa topik ini sudah dijawab, tanpa membawa seluruh tabel data.
            if len(content) > _MAX_ASSISTANT_CONTENT:
                content = content[:_MAX_ASSISTANT_CONTENT] + "… [ringkasan, data lengkap tersedia via tool jika dibutuhkan]"
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
[Panduan Format Pemikiran (Thought Process)]

Setiap kali kamu menulis "Thought:", WAJIB SINGKAT — maksimal 2-3 kalimat.
Format yang benar:
  Thought: User ingin [X]. Saya akan memanggil tool [Y] untuk mendapatkan data.
  (lalu langsung tulis Action)

Hindari format berikut untuk mencegah error:
  Thought: Baiklah, saya perlu mempertimbangkan bahwa... [paragraf panjang]
  Thought: Menganalisis permintaan user secara mendalam... [repetisi panduan]

Setelah menerima hasil tool → LANGSUNG tulis "Final Answer:" tanpa Thought tambahan.

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
   Pastikan output terakhir hanya menggunakan teks natural, bukan JSON, "Action:", "Thought:", atau format internal apapun.
   Gunakan angka dari output tool — JANGAN tebak-tebak.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

_MAX_STORED_ANSWER_LEN: int = 500

def _compress_for_history(answer: str) -> str:
    """Ringkas jawaban panjang sebelum disimpan ke session history.

    Strategi: ambil 500 karakter pertama + tag ringkasan.
    Ini cukup untuk memberi tahu agent bahwa topik sudah dijawab,
    tanpa membawa seluruh tabel data ke prompt berikutnya.
    """
    if len(answer) <= _MAX_STORED_ANSWER_LEN:
        return answer
    return answer[:_MAX_STORED_ANSWER_LEN] + "\n… [jawaban dipotong untuk efisiensi konteks. Panggil tool kembali jika detail lengkap dibutuhkan.]"
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

    # Gunakan singleton LLM dan Agent — tidak re-inisialisasi per request.
    # Context percakapan & user_id disuntikkan via task description di bawah.
    agent: Any = _get_agent()

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
        # verbose=True di-hardcode agar log rich CrewAI (kotak ASCII) selalu
        # tampil di stdout terminal tanpa bergantung environment/settings.
        verbose=True,
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


# ── Step text extractor ───────────────────────────────────────────────────────

def _extract_step_text(step_output: Any) -> str:
    """Normalisasi output step_callback dari berbagai versi CrewAI.

    CrewAI memanggil step_callback dengan tipe yang berbeda tergantung versi:
      - str          : versi lama, langsung teks
      - AgentAction  : has .tool, .tool_input, .log
      - AgentFinish  : has .return_values["output"]
      - TaskOutput   : has .raw atau .output
      - dict         : fallback internal

    Fungsi ini mencoba semua kemungkinan secara berurutan dan mengembalikan
    teks yang bermakna (bukan raw repr objek).
    """
    if not step_output:
        return ""

    # String langsung
    if isinstance(step_output, str):
        return step_output.strip()[:400]

    # AgentFinish (langchain-style): return_values["output"]
    if hasattr(step_output, "return_values"):
        rv = step_output.return_values
        if isinstance(rv, dict):
            return str(rv.get("output", rv)).strip()[:400]

    # AgentAction (langchain-style): log berisi Thought + Action
    if hasattr(step_output, "log") and step_output.log:
        return str(step_output.log).strip()[:400]

    # CrewAI TaskOutput: .raw atau .output
    if hasattr(step_output, "raw") and step_output.raw:
        return str(step_output.raw).strip()[:400]
    if hasattr(step_output, "output") and step_output.output:
        return str(step_output.output).strip()[:400]

    # Umum: .text
    if hasattr(step_output, "text") and step_output.text:
        return str(step_output.text).strip()[:400]

    # Dict fallback
    if isinstance(step_output, dict):
        for key in ("output", "text", "result", "content"):
            if step_output.get(key):
                return str(step_output[key]).strip()[:400]

    return str(step_output).strip()[:400]


# ── Async entry point (digunakan oleh streaming SSE di main.py) ───────────────

async def run_crew_async(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
    step_queue: "asyncio.Queue[str | None] | None" = None,
) -> str:
    """Jalankan Crew secara async menggunakan kickoff_async().

    Perbedaan utama dengan run_crew():
      - Menggunakan crew.kickoff_async() yang internally memanggil
        asyncio.to_thread(), sehingga TIDAK mem-block event loop FastAPI.
      - Menerima step_queue opsional sebagai jembatan antara step_callback
        CrewAI (berjalan di worker thread) dan async SSE generator di main.py.
        Setiap step agent di-push ke queue → generator konsumsi → stream ke client.

    Aliran data saat step_queue tersedia:
      CrewAI thread → step_callback() → run_coroutine_threadsafe(queue.put) →
      asyncio.Queue → _stream_crew_response() generator → SSE → client browser.

    Args:
        user_message  : Query user terbaru.
        glpi_user_id  : GLPI User ID (0 untuk query umum).
        messages      : Riwayat percakapan lengkap.
        step_queue    : asyncio.Queue untuk streaming thought/step ke SSE.
                        None = tidak ada streaming thought (hanya keep-alive).
                        Sentinel None di-put setelah crew selesai/error.

    Returns:
        Jawaban final yang sudah di-sanitize.
    """
    all_messages: list[dict[str, str]] = messages or []
    agent: Any = _get_agent()

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

    # ── Bangun step_callback jika step_queue tersedia ─────────────────────
    # PENTING: step_callback dipanggil dari worker thread (bukan event loop).
    # Gunakan run_coroutine_threadsafe() — BUKAN await — untuk push ke queue.
    step_callback_fn: Any = None
    if step_queue is not None:
        loop = asyncio.get_running_loop()

        def _step_callback(step_output: Any) -> None:
            text = _extract_step_text(step_output)
            if text:
                asyncio.run_coroutine_threadsafe(
                    step_queue.put(text), loop
                )

        step_callback_fn = _step_callback

    crew: Crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        **({"step_callback": step_callback_fn} if step_callback_fn else {}),
    )

    prior_turns = max(0, len([m for m in all_messages if m.get("role") == "user"]) - 1)
    logger.info(
        "Crew kickoff_async | user_id=%s | prior_turns=%d | queue=%s | msg='%.80s'",
        glpi_user_id,
        prior_turns,
        "yes" if step_queue else "no",
        user_message,
    )

    try:
        # kickoff_async() internaly calls asyncio.to_thread(self.kickoff)
        # sehingga tidak mem-block event loop FastAPI.
        result: Any = await crew.kickoff_async()
        clean_str = sanitize_agent_output(str(result))

        logger.info(
            "Crew async done | user_id=%s | result='%.120s'",
            glpi_user_id,
            clean_str,
        )
        return clean_str

    except Exception as exc:
        logger.error("Crew async execution failed: %s", exc, exc_info=True)
        return "Mohon maaf, sistem sedang mengalami kendala teknis. Silakan coba beberapa saat lagi."

    finally:
        # Selalu kirim sentinel None ke queue agar generator tidak hang
        # menunggu item berikutnya setelah crew selesai/error.
        if step_queue is not None:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    step_queue.put(None), loop
                ).result(timeout=2)
            except Exception:
                pass  # Abaikan error saat cleanup