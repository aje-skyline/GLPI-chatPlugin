"""Test sanitizer — strip toolcall tags & fallback pesan.

Memastikan ``sanitize_agent_output`` membersihkan tag XML-style
``<toolcall>`` dari output agent dan mengembalikan pesan fallback
Bahasa Indonesia ketika seluruh konten terdeteksi sebagai format
internal agent.
"""

from __future__ import annotations

from app.utils import sanitize_agent_output


def test_strips_toolcall_tags():
    """Tag <toolcall> harus dihapus dari output agent."""
    raw = (
        "Final Answer: <toolcall>count_all_computers</toolcall>"
        "Total komputer adalah 500 unit."
    )
    result = sanitize_agent_output(raw)

    assert "<toolcall>" not in result, "tag <toolcall> harus ter-strip"
    assert "</toolcall>" not in result, "tag </toolcall> harus ter-strip"
    assert "Total komputer adalah 500 unit." in result


def test_empty_after_clean_returns_fallback():
    """Jika seluruh konten format internal → kembalikan pesan fallback."""
    raw = (
        "Thought: Saya perlu memanggil tool untuk menghitung komputer.\n"
        "Action: count_all_computers\n"
        "Observation: 500 unit ditemukan.\n"
        "Thought: Sekarang saya bisa menjawab."
    )
    result = sanitize_agent_output(raw)

    assert "Mohon maaf" in result, "harus mengembalikan pesan fallback"
    assert "Thought" not in result, "format internal tidak boleh bocor"


def test_normal_answer_passthrough():
    """Jawaban bersih tanpa format internal → tidak berubah."""
    raw = "Total komputer adalah 500 unit."
    result = sanitize_agent_output(raw)

    assert result == raw
