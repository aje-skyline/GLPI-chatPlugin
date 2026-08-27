"""Shared utilities — GLPI AI Gateway.

Single source of truth untuk sanitasi output agent. Diimpor oleh
crew_services.py agar logika tidak terduplikasi.

Meskipun CrewAI native LLM menangani tool calling via JSON secara internal,
agent ReAct masih bisa bocor format "Thought:/Action:" ke Final Answer
(terbukti dari log produksi). Sanitizer ini adalah safety net terakhir.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Pola baris yang bocor dari format internal agent ─────────────────────────
_AGENT_LEAK_PATTERN = re.compile(
    r"^\s*("
    r"Thought|Action\s+Input|Action|Observation"
    r"|I need to|I will|I should"
    r"|Let me|I'll|First,?\s+I|Now\s+I"
    r")\s*[:\-]",
    re.IGNORECASE,
)

# ── Pola tag XML-style tool call yang bocor dari agent ReAct ──────────────────
_TOOLCALL_TAG_PATTERN = re.compile(
    r"</?(?:toolcall|tool_call|function_call)[^>]*>",
    re.IGNORECASE,
)


def sanitize_agent_output(raw: str) -> str:
    """Bersihkan format internal agent dari output CrewAI.

    Strategi (diterapkan berurutan):
      1. Jika ada ``Final Answer:`` → ambil hanya teks setelahnya.
      1.5. Strip tag XML-style ``<toolcall>`` / ``<tool_call>`` /
           ``<function_call>`` dari seluruh teks.
      2. Drop semua baris yang dimulai dengan keyword internal agent
         beserta seluruh "blok" berikutnya (hingga baris kosong berikutnya).
      3. Strip whitespace.
      4. Jika hasil kosong → log warning dan kembalikan pesan fallback
         Bahasa Indonesia (lebih baik pesan jelas daripada format internal
         yang bocor ke user).

    Args:
        raw: String mentah dari ``crew.kickoff()`` atau output agent manapun.

    Returns:
        String bersih siap ditampilkan ke user.
    """
    if not raw:
        return raw

    text = raw.strip()

    # Strategi 1: ambil setelah "Final Answer:"
    fa_match = re.search(r"(?i)final\s+answer\s*:", text)
    if fa_match:
        text = text[fa_match.end():].strip()

    # Strategi 1.5: strip tag XML-style tool call dari seluruh teks
    text = _TOOLCALL_TAG_PATTERN.sub("", text)

    # Strategi 2: drop baris keyword dan satu blok setelahnya
    clean_lines: list[str] = []
    skip_block = False

    for line in text.splitlines():
        stripped = line.strip()

        if skip_block:
            if stripped == "":
                skip_block = False
            continue

        if _AGENT_LEAK_PATTERN.match(stripped):
            skip_block = True
            continue

        clean_lines.append(line)

    cleaned = "\n".join(clean_lines).strip()

    if not cleaned:
        logger.warning(
            "sanitize_agent_output: hasil bersih kosong, mengembalikan pesan fallback"
        )
        return (
            "Mohon maaf, sistem tidak dapat memproses permintaan Anda "
            "saat ini. Silakan coba lagi."
        )

    return cleaned