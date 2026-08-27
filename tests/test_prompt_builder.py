"""Test prompt builder — Thought format dihapus, ATURAN DATA BESAR dipertahankan.

Memastikan ``_build_task_description`` tidak lagi menyertakan blok
``[Panduan Format Pemikiran (Thought Process)]`` yang menyebabkan model
menulis tool call sebagai teks alih-alih memakai native function calling.
Blok ``ATURAN DATA BESAR`` dan flag ``[INSTRUKSI SISTEM]`` tetap ada.
"""

from __future__ import annotations

from app.agents.prompt_builder import _build_task_description


def test_no_thought_format_instruction():
    """Blok Thought format tidak boleh ada di task description."""
    desc = _build_task_description("Berapa total?", 0, [])

    assert "Thought: User ingin" not in desc, (
        "instruksi format Thought harus dihapus agar model pakai native "
        "function calling API"
    )
    assert "Panduan Format Pemikiran" not in desc, (
        "header blok [Panduan Format Pemikiran] harus dihapus"
    )


def test_data_besar_guidance_preserved():
    """Blok ATURAN DATA BESAR & referensi INSTRUKSI SISTEM tetap dipertahankan."""
    desc = _build_task_description("Berapa total?", 0, [])

    assert "ATURAN DATA BESAR" in desc, (
        "blok ATURAN DATA BESAR tidak boleh terhapus"
    )
    assert "INSTRUKSI SISTEM" in desc, (
        "referensi [INSTRUKSI SISTEM] harus tetap ada untuk panduan data besar"
    )
