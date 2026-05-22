"""app/tools/contract_tools.py — Contract Tools.

Berisi CrewAI Tool khusus untuk domain kontrak GLPI:

  Contracts:
    - CountContractsTool       (count_contracts)
    - GetContractsTool         (list_all_contracts)
    - GetContractDetailTool    (get_contract_detail)

ATURAN ARSITEKTUR:
  - Pengambilan data HANYA melalui app.repository.contract_repository.
    (Bukan asset_repository — kontrak adalah domain terpisah dari aset komputer.)
  - Eksekusi async HANYA melalui app.infrastructure.async_runner.run_async.
  - Formatting output dilakukan inline di sini (data cukup sederhana, tidak
    memerlukan formatter khusus yang perlu di-share).
  - Tidak boleh ada import dari app.it_glpi_client secara langsung.

SMART PAGINATION:
  GetContractsTool menerapkan pola "Smart Pagination" untuk mencegah token
  explosion saat jumlah kontrak besar (≥ _DISPLAY_LIMIT). Jika data dipotong,
  tool menyisipkan flag [INSTRUKSI SISTEM — WAJIB DIIKUTI] sebagai sinyal
  "lampu merah" agar Agent langsung menulis Final Answer tanpa retry/looping.
  Pola ini konsisten dengan Computer dan Supplier tools.

CHANGELOG:
  v1.0 — Dipecah dari ticket_tools.py (Refactor Contract Domain).
          Memindahkan GetContractsTool dan GetContractDetailTool beserta
          Input Schema-nya. Memperbaiki bug import: menggunakan
          contract_repository (bukan asset_repository) sesuai Clean Architecture.
  v1.1 — Implementasi Smart Pagination pada GetContractsTool.
          Tambah parameter limit pada GetContractsInput (default 5, maks 50).
          Output dipotong ke _DISPLAY_LIMIT jika total > threshold, dengan
          flag [INSTRUKSI SISTEM] untuk mencegah Agent looping/retry.
  v1.2 — Tambah CountContractsTool. Perbaiki typo len(results). Sambungkan
          parameter limit dari input schema ke repository call.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.async_runner import run_async
from app.repository import contract_repository

logger = logging.getLogger(__name__)

# ── Smart Pagination Constants ────────────────────────────────────────────────
# Batas jumlah item yang ditampilkan ke LLM per satu tool call.
# Di atas threshold ini, output dipotong dan flag [INSTRUKSI SISTEM] disisipkan.
# Nilai 5 konsisten dengan pola get_suppliers(limit=5) pada SupplierTools.
_DISPLAY_LIMIT: int = 5

# Threshold minimum sebelum pagination aktif.
# Jika total data ≤ _PAGINATION_THRESHOLD, semua data ditampilkan tanpa flag.
# Memberi ruang untuk query filter (misal: kontrak per komputer) yang hasilnya
# biasanya sedikit dan tidak perlu dipotong.
_PAGINATION_THRESHOLD: int = 10


# ══════════════════════════════════════════════════════════════════════════════
# Input Schemas
# ══════════════════════════════════════════════════════════════════════════════

class CountContractInput(BaseModel):
    """Schema kosong — count_contracts tidak memerlukan parameter."""
    pass


class GetContractsInput(BaseModel):
    computer_id: int = Field(
        default=0,
        ge=0,
        description="ID komputer (opsional). Jika 0, ambil semua kontrak.",
    )
    active_only: bool = Field(
        default=False,
        description="Jika True, filter hanya kontrak yang masih aktif.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maksimal 10 sampel untuk mencegah token overflow.",
    )


class GetContractDetailInput(BaseModel):
    contract_id: int = Field(
        ...,
        gt=0,
        description="ID kontrak di GLPI.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Contracts
# ══════════════════════════════════════════════════════════════════════════════

class CountContractsTool(BaseTool):
    """Hitung jumlah total kontrak di GLPI secara cepat (1 API call)."""

    name: str = "count_contracts"
    description: str = (
        "Hitung jumlah total kontrak yang terdaftar di GLPI. "
        "Gunakan untuk pertanyaan: 'berapa jumlah kontrak?', 'total kontrak ada berapa?'. "
        "Lebih cepat dan hemat token dibanding list_all_contracts."
    )
    args_schema: Type[BaseModel] = CountContractInput

    def _run(self) -> str:
        try:
            total = run_async(contract_repository.count_contracts())
            return f"Total terdapat {total} kontrak terdaftar di GLPI."
        except Exception as exc:
            logger.error("CountContractsTool failed: %s", exc)
            return f"Gagal menghitung kontrak: {exc}"


class GetContractsTool(BaseTool):
    """Daftar kontrak GLPI dengan Smart Pagination."""

    name: str = "list_all_contracts"
    description: str = (
        "Tampilkan daftar kontrak GLPI. "
        "Mengembalikan sampel 5 data terbaru beserta total count exact. "
        "Gunakan untuk: 'daftar kontrak', 'tampilkan kontrak aktif', "
        "'kontrak milik komputer ID X'."
    )
    args_schema: Type[BaseModel] = GetContractsInput

    def _run(
        self,
        computer_id: int = 0,
        active_only: bool = False,
        limit: int = 5,
    ) -> str:
        try:
            # Ambil total count dan sampel data secara paralel-logis
            total_count = run_async(contract_repository.count_contracts())
            results = run_async(
                contract_repository.get_contracts(
                    computer_id=computer_id,
                    limit=limit,           # ← diteruskan dari input schema (bug fix)
                )
            )

            if not results:
                return "Tidak ada kontrak ditemukan."

            # Filter active_only jika diminta (end_date >= hari ini atau kosong)
            if active_only:
                import datetime
                today = datetime.date.today().isoformat()
                results = [
                    c for c in results
                    if not c.get("end_date") or c["end_date"] >= today
                ]
                if not results:
                    return "Tidak ada kontrak aktif ditemukan."

            output = f"Total: {total_count} kontrak ditemukan di GLPI.\n"
            output += f"Menampilkan {len(results)} sampel terbaru:\n\n"  # ← fix: len() bukan le()

            for c in results:
                output += (
                f"• **{c.get('name') or '-'}** (ID: {c.get('id') or '-'}) "f"No: {c.get('num') or '-'} | Sup: {c.get('supplier') or '-'} | Ent: {c.get('entity') or '-'} | Biaya: {c.get('cost') or '-'} | Berakhir:{c.get('end_date') or '-'}\n"
                )

            # Sisipkan flag Smart Pagination jika data di-truncate
            if total_count > len(results):
                output += "\n**[INSTRUKSI SISTEM — WAJIB DIIKUTI]**\n"
                output += f"Terdapat total {total_count} kontrak. Data di atas hanya sampel.\n"
                output += (
                    "JANGAN panggil tool lagi. Beritahu user jumlah total dan sampaikan "
                    "jika ingin mencari kontrak spesifik silakan sebutkan nama atau ID-nya."
                )

            return output

        except Exception as exc:
            logger.error("GetContractsTool failed: %s", exc)
            return f"Gagal mengambil daftar kontrak: {exc}"


class GetContractDetailTool(BaseTool):
    """Ambil detail lengkap satu kontrak berdasarkan ID-nya."""

    name: str = "get_contract_detail"
    description: str = (
        "Ambil detail lengkap satu kontrak berdasarkan ID-nya. "
        "Gunakan setelah mendapatkan contract_id dari list_all_contracts."
    )
    args_schema: Type[BaseModel] = GetContractDetailInput

    def _run(self, contract_id: int) -> str:
        try:
            c: dict[str, Any] | None = run_async(
                contract_repository.get_contract_by_id(contract_id)
            )
            if not c:
                return f"Kontrak dengan ID {contract_id} tidak ditemukan di GLPI."

            output  = f"Detail Kontrak (ID: {contract_id}):\n\n"
            output += f"  Nama     : {c.get('name')       or '-'}\n"
            output += f"  Nomor    : {c.get('num')        or '(tidak ada)'}\n"
            output += f"  Supplier : {c.get('supplier')   or '(tidak ada)'}\n"
            output += f"  Entitas  : {c.get('entity')     or '(tidak ada)'}\n"
            output += f"  Biaya    : {c.get('cost')       or '(tidak ada)'}\n"
            output += f"  Tipe     : {c.get('type')       or '(tidak ada)'}\n"
            output += f"  Mulai    : {c.get('begin_date') or '(tidak ada)'}\n"
            output += f"  Durasi   : {c.get('duration')   or '(tidak ada)'} bulan\n"
            output += f"  Berakhir : {c.get('end_date')   or '(tidak ada)'}\n"
            if c.get("comment"):
                output += f"  Catatan  : {c['comment']}\n"
            return output

        except Exception as exc:
            logger.error("GetContractDetailTool failed: %s", exc)
            return f"Gagal mengambil detail kontrak: {exc}"