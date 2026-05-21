"""app/services/crew_orchestrator.py — Crew Execution Orchestrator.

Menggantikan crew_services.py sebagai entry point tunggal untuk eksekusi CrewAI.

TANGGUNG JAWAB FILE INI:
  1. Menerima input user (pesan + riwayat + user_id).
  2. Memanggil prompt_builder untuk merakit task description.
  3. Mengambil singleton agent dari agent_factory.
  4. Membentuk Crew dan menjalankan eksekusi (blocking atau async + streaming SSE).
  5. Men-sanitize output dan menangani error.

YANG TIDAK ADA DI SINI (sudah dipindah):
  - Konfigurasi LLM             → app.agents.agent_factory._get_llm()
  - Build Agent                  → app.agents.agent_factory.build_it_support()
  - Perangkaian prompt/history   → app.agents.prompt_builder
  - Definisi tools               → app.tools

CHANGELOG:
  v1.0 — Dipecah dari crew_services.py (Tahap 4 Clean Architecture).
          run_crew() dan run_crew_async() tetap dengan signature yang sama
          agar main.py tidak perlu diubah sama sekali.
          _extract_step_text() dan _preserve_crewai_stdout() dipertahankan
          di sini karena merupakan bagian dari mekanisme eksekusi, bukan
          presentasi data maupun perakitan prompt.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from crewai import Crew, Process, Task

from app.agents.agent_factory import _get_agent
from app.agents.prompt_builder import _build_task_description
from app.utils import sanitize_agent_output

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# stdout Guard
# ══════════════════════════════════════════════════════════════════════════════

def _preserve_crewai_stdout() -> None:
    """Pastikan sys.stdout tidak pernah diganti dengan NullWriter-like object.

    CrewAI mencetak via rich.Console(stderr=False) yang membaca sys.stdout
    pada saat print. Jika uvicorn sudah me-redirect stdout, kembalikan ke
    sys.__stdout__ agar kotak ASCII rich tetap terlihat di terminal.

    Dipanggil sekali saat module ini di-import (baris paling bawah fungsi ini).
    """
    try:
        if not hasattr(sys.stdout, "fileno"):
            sys.stdout = sys.__stdout__
            return
        sys.stdout.fileno()
    except Exception:
        sys.stdout = sys.__stdout__


# Jalankan guard segera saat module di-import agar rich sudah mendapatkan
# stdout yang valid sebelum Crew pertama kali diinisialisasi.
_preserve_crewai_stdout()


# ══════════════════════════════════════════════════════════════════════════════
# Step Output Normalizer
# ══════════════════════════════════════════════════════════════════════════════

def _extract_step_text(step_output: Any) -> str:
    """Normalisasi output step_callback dari berbagai versi CrewAI.

    CrewAI memanggil step_callback dengan tipe yang berbeda tergantung versi:
      - str          : versi lama, langsung teks
      - AgentAction  : has .tool, .tool_input, .log
      - AgentFinish  : has .return_values["output"]
      - TaskOutput   : has .raw atau .output
      - dict         : fallback internal

    Fungsi ini mencoba semua kemungkinan secara berurutan dan mengembalikan
    teks yang bermakna (bukan raw repr objek). Output dipotong ke 400 karakter
    karena hanya digunakan sebagai preview streaming SSE, bukan sebagai
    konten final.

    Args:
        step_output: Object apa pun yang dikirimkan CrewAI ke step_callback.

    Returns:
        String teks bermakna (maksimal 400 karakter), atau "" jika tidak ada.
    """
    if not step_output:
        return ""

    # String langsung (versi lama CrewAI)
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

    # Fallback umum: .text
    if hasattr(step_output, "text") and step_output.text:
        return str(step_output.text).strip()[:400]

    # Dict fallback
    if isinstance(step_output, dict):
        for key in ("output", "text", "result", "content"):
            if step_output.get(key):
                return str(step_output[key]).strip()[:400]

    return str(step_output).strip()[:400]


# ══════════════════════════════════════════════════════════════════════════════
# Blocking Entrypoint
# ══════════════════════════════════════════════════════════════════════════════

def run_crew(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
) -> str:
    """Jalankan CrewAI Crew untuk memproses satu query user GLPI (blocking).

    Ini adalah blocking call — panggil via `loop.run_in_executor` dari
    konteks async (sudah dilakukan di main.py).

    Flow:
      1. Rakit task description via prompt_builder.
      2. Buat Task + Crew menggunakan singleton Agent dari agent_factory.
      3. Jalankan crew.kickoff() secara synchronous.
      4. Sanitize dan kembalikan output.

    Args:
        user_message  : Query user terbaru.
        glpi_user_id  : GLPI User ID (0 untuk query umum).
        messages      : Riwayat percakapan lengkap termasuk turn saat ini.

    Returns:
        Jawaban final yang sudah di-sanitize, siap ditampilkan ke user.
        Mengembalikan pesan error generik jika Crew gagal.
    """
    all_messages: list[dict[str, str]] = messages or []

    # Gunakan singleton Agent — tidak re-inisialisasi per request.
    # Context percakapan & user_id disuntikkan via task description.
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

    prior_turns = max(
        0, len([m for m in all_messages if m.get("role") == "user"]) - 1
    )
    logger.info(
        "Crew kickoff | user_id=%s | prior_turns=%d | msg='%.80s'",
        glpi_user_id,
        prior_turns,
        user_message,
    )

    try:
        result: Any  = crew.kickoff()
        clean_str    = sanitize_agent_output(str(result))

        logger.info(
            "Crew done | user_id=%s | result='%.120s'",
            glpi_user_id,
            clean_str,
        )
        return clean_str

    except Exception as exc:
        logger.error("Crew execution failed: %s", exc, exc_info=True)
        return (
            "Mohon maaf, sistem sedang mengalami kendala teknis. "
            "Silakan coba beberapa saat lagi."
        )


# ══════════════════════════════════════════════════════════════════════════════
# Async + Streaming Entrypoint
# ══════════════════════════════════════════════════════════════════════════════

async def run_crew_async(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
    step_queue: "asyncio.Queue[str | None] | None" = None,
) -> str:
    """Jalankan Crew secara async menggunakan kickoff_async() + SSE streaming.

    Perbedaan utama dengan run_crew():
      - Menggunakan crew.kickoff_async() yang internally memanggil
        asyncio.to_thread(), sehingga TIDAK mem-block event loop FastAPI.
      - Menerima step_queue opsional sebagai jembatan antara step_callback
        CrewAI (berjalan di worker thread) dan async SSE generator di main.py.

    Aliran data saat step_queue tersedia:
      CrewAI thread → step_callback() → run_coroutine_threadsafe(queue.put) →
      asyncio.Queue → _stream_crew_response() generator → SSE → client browser.

    Thread-safety step_callback:
      step_callback dipanggil dari worker thread CrewAI, BUKAN dari event loop
      FastAPI. Oleh karena itu, push ke asyncio.Queue HARUS menggunakan
      run_coroutine_threadsafe(), bukan await. Loop di-capture saat
      run_crew_async() dipanggil (masih di event loop) dan diteruskan ke
      closure _step_callback agar worker thread dapat mengaksesnya.

    Args:
        user_message  : Query user terbaru.
        glpi_user_id  : GLPI User ID (0 untuk query umum).
        messages      : Riwayat percakapan lengkap.
        step_queue    : asyncio.Queue untuk streaming thought/step ke SSE.
                        None = tidak ada streaming thought (hanya keep-alive).
                        Sentinel None di-put setelah crew selesai/error agar
                        generator SSE tidak hang menunggu item berikutnya.

    Returns:
        Jawaban final yang sudah di-sanitize.
        Mengembalikan pesan error generik jika Crew gagal.
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

    # ── Bangun step_callback jika step_queue tersedia ─────────────────────────
    # PENTING: step_callback dipanggil dari worker thread CrewAI (bukan event loop).
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

    prior_turns = max(
        0, len([m for m in all_messages if m.get("role") == "user"]) - 1
    )
    logger.info(
        "Crew kickoff_async | user_id=%s | prior_turns=%d | queue=%s | msg='%.80s'",
        glpi_user_id,
        prior_turns,
        "yes" if step_queue else "no",
        user_message,
    )

    try:
        # kickoff_async() internally calls asyncio.to_thread(self.kickoff)
        # sehingga tidak mem-block event loop FastAPI.
        result: Any = await crew.kickoff_async()
        clean_str   = sanitize_agent_output(str(result))

        logger.info(
            "Crew async done | user_id=%s | result='%.120s'",
            glpi_user_id,
            clean_str,
        )
        return clean_str

    except Exception as exc:
        logger.error("Crew async execution failed: %s", exc, exc_info=True)
        return (
            "Mohon maaf, sistem sedang mengalami kendala teknis. "
            "Silakan coba beberapa saat lagi."
        )

    finally:
        # Selalu kirim sentinel None ke queue agar generator SSE tidak hang
        # menunggu item berikutnya setelah crew selesai atau error.
        if step_queue is not None:
            try:
                _loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    step_queue.put(None), _loop
                ).result(timeout=2)
            except Exception:
                pass  # Abaikan error saat cleanup — crew sudah selesai