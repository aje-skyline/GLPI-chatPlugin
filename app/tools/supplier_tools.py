"""app/tools/supplier_tools.py — Supplier Domain Tools.

Berisi seluruh CrewAI Tool yang berhubungan dengan supplier/vendor di GLPI:

  - CountSuppliersTool  (count_suppliers)  — hitung total tanpa fetch list
  - SearchSuppliersTool (get_suppliers)    — cari/list supplier dengan filter

CATATAN PERFORMA:
  Setelah refactor repository ke single-call forcedisplay, limit default
  dinaikkan ke 20 (get) dan batas atas ke 50 tanpa risiko timeout.
  Sebelumnya: limit=5 karena N+1 calls (50 supplier = ~51 API calls, ~45s+)
  Sekarang  : limit=20 aman karena 50 supplier = 1 API call (< 3 detik)

ATURAN ARSITEKTUR:
  - Pengambilan data HANYA melalui app.repository.supplier_repository.
  - Eksekusi async HANYA melalui app.infrastructure.async_runner.run_async.
  - Formatting output HANYA melalui app.tools.formatters.
  - Tidak boleh ada import dari app.it_glpi_client secara langsung.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.async_runner import run_async
from app.repository import supplier_repository
from app.repository.supplier_repository import PagedResult
from app.tools.formatters import _render_supplier_result

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Input Schemas
# ══════════════════════════════════════════════════════════════════════════════

class CountSuppliersInput(BaseModel):
    """Input schema untuk CountSuppliersTool — tidak ada parameter yang diperlukan."""

    call_id: str = Field(default="", exclude=True)


class SupplierSearchInput(BaseModel):
    """Input schema untuk SearchSuppliersTool.

    Semua parameter filter bersifat opsional.
    Kosongkan semua filter untuk menampilkan semua supplier.

    Batas limit: 1–50. Default: 20.
    Limit dinaikkan karena repository kini menggunakan single API call
    (forcedisplay), sehingga mengambil 50 supplier tidak lebih lambat
    dari mengambil 5 supplier (tetap 1 API call).

    Jika ingin mengetahui JUMLAH TOTAL supplier saja (tanpa list),
    gunakan tool count_suppliers — lebih cepat dan tidak butuh limit besar.
    """

    name:    Optional[str] = Field(
        default=None,
        description="Filter nama supplier (partial match).",
    )
    entity:  Optional[str] = Field(
        default=None,
        description="Filter entity/organisasi GLPI.",
    )
    address: Optional[str] = Field(
        default=None,
        description="Filter alamat (kota, jalan, dll).",
    )
    phone:   Optional[str] = Field(
        default=None,
        description="Filter nomor telepon.",
    )
    fax:     Optional[str] = Field(
        default=None,
        description="Filter nomor fax.",
    )
    email:   Optional[str] = Field(
        default=None,
        description="Filter alamat email.",
    )
    limit:   int = Field(
        default=20,
        ge=1,
        le=50,
        description=(
            "Jumlah maksimal hasil (1–50, default 20). "
            "Mengambil 50 supplier hanya membutuhkan 1 API call — "
            "tidak ada overhead N+1 seperti sebelumnya. "
            "Gunakan count_suppliers jika hanya butuh angka total."
        ),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tools
# ══════════════════════════════════════════════════════════════════════════════

class CountSuppliersTool(BaseTool):
    """Hitung jumlah total supplier di GLPI (cepat, 1 API call)."""

    name: str = "count_suppliers"
    description: str = (
        "Hitung jumlah TOTAL supplier/vendor yang terdaftar di GLPI. "
        "Sangat cepat (1 API call). "
        "Gunakan HANYA saat user bertanya 'ada berapa supplier', "
        "'total vendor', atau pertanyaan count supplier tanpa filter. "
        "Untuk list atau cari supplier, gunakan get_suppliers."
    )
    args_schema: Type[BaseModel] = CountSuppliersInput
    cache_function: Any = Field(default=lambda *args, **kwargs: False)

    def _run(self, **kwargs: Any) -> str:
        try:
            total: int = run_async(supplier_repository.count_suppliers())
            total_fmt  = f"{total:,}".replace(",", ".")
            logger.info("CountSuppliersTool: total=%d", total)
            return f"Total supplier terdaftar di GLPI: **{total_fmt}** supplier."
        except Exception as exc:
            logger.error("CountSuppliersTool failed: %s", exc)
            return f"Gagal menghitung jumlah supplier: {exc}"


class SearchSuppliersTool(BaseTool):
    """Cari supplier/vendor di GLPI dengan filter dinamis.

    Menggunakan single API call dengan forcedisplay lengkap.
    Mendukung pencarian berdasarkan 6 kolom utama: Name, Entity,
    Address, Phone, Fax, Email.
    """

    name: str = "get_suppliers"
    description: str = (
        "Cari dan tampilkan daftar supplier/vendor yang terdaftar di GLPI. "
        "Mendukung filter opsional: name, entity, address, phone, fax, email. "
        "Secara default menampilkan 20 supplier terbaru. "
        "Bisa menampilkan hingga 50 supplier sekaligus tanpa risiko timeout "
        "karena menggunakan 1 API call (forcedisplay). "
        "Output per supplier: Nama, Entity, Alamat, Telepon, Fax, Email. "
        "Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."
    )
    args_schema: Type[BaseModel] = SupplierSearchInput

    def _run(
        self,
        name:    Optional[str] = None,
        entity:  Optional[str] = None,
        address: Optional[str] = None,
        phone:   Optional[str] = None,
        fax:     Optional[str] = None,
        email:   Optional[str] = None,
        limit:   int = 20,
        **kwargs: Any,  # Robustness: tolerate extra fields from LLM
    ) -> str:
        # Bangun label filter untuk output yang informatif
        active_filters: list[str] = []
        if name:    active_filters.append(f"nama='{name}'")
        if entity:  active_filters.append(f"entity='{entity}'")
        if address: active_filters.append(f"alamat='{address}'")
        if phone:   active_filters.append(f"telepon='{phone}'")
        if fax:     active_filters.append(f"fax='{fax}'")
        if email:   active_filters.append(f"email='{email}'")

        filter_label = (
            f"dengan filter {', '.join(active_filters)}"
            if active_filters else ""
        )

        logger.info(
            "Tool SearchSuppliers | filters=%s | limit=%d",
            active_filters, limit,
        )

        try:
            result: PagedResult = run_async(
                supplier_repository.search_suppliers(
                    name=name,
                    entity=entity,
                    address=address,
                    phone=phone,
                    fax=fax,
                    email=email,
                    limit=limit,
                ),
                # Timeout diturunkan drastis: single API call seharusnya
                # selesai dalam < 10 detik bahkan untuk 50 supplier.
                # 20 detik adalah headroom 2x yang sangat konservatif.
                timeout=20.0,
            )
            output = _render_supplier_result(result, filter_label=filter_label)
            output += f"\n\n[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {result['totalcount']}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."
            return output

        except Exception as exc:
            logger.error("SearchSuppliersTool failed: %s", exc, exc_info=True)
            return f"Gagal mengambil data supplier: {exc}"