"""app/tools/computer_tools.py — Computer Domain Tools.

Berisi seluruh CrewAI Tool yang berhubungan dengan aset komputer di GLPI:

  - GetUserAssetsTool          (get_user_assets)
  - GetAllComputersTool        (get_all_computers)
  - GetComputerDetailTool      (get_computer_detail)
  - CountAllComputersTool      (count_all_computers)
  - SearchComputerByNameTool   (search_computer_by_name)
  - SearchComputerTool         (search_computer)
  - GetComputersByStatusTool   (get_computers_by_status)
  - GetComputersByLocationTool (get_computers_by_location)
  - GetComputersByOsTool       (get_computers_by_os)

ATURAN ARSITEKTUR:
  - Pengambilan data HANYA melalui app.repository.asset_repository.
  - Eksekusi async HANYA melalui app.infrastructure.async_runner.run_async.
  - Formatting output HANYA melalui app.tools.formatters.
  - Tidak boleh ada import dari app.it_glpi_client secara langsung.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.async_runner import run_async
from app.repository import asset_repository
from app.repository.asset_repository import PagedResult
from app.tools.formatters import (
    _fmt_computer_full_detail,
    _fmt_computer_row,
    _render_paged_result,
)
from app.cache_count import get_count_cache, set_count_cache
from app.infrastructure.thread_context import get_session_id

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Input Schemas
# ══════════════════════════════════════════════════════════════════════════════

class GetUserAssetsInput(BaseModel):
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI. Gunakan 0 jika tidak diketahui.",
    )


class GetAllComputersInput(BaseModel):
    sample_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description=(
            "Jumlah komputer yang ditampilkan sebagai sample (default 50). "
            "Nilai exact totalcount SELALU dikembalikan terlepas dari parameter ini."
        ),
    )
    has_serial: bool = Field(
        default=False,
        description="Jika True, hanya kembalikan komputer yang memiliki serial number.",
    )
    paginate: bool = Field(
        default=True,
        description=(
            "Jika True (default), gunakan auto-pagination untuk mendapatkan totalcount "
            "yang akurat dari seluruh database. Jika False, hanya ambil sample_size record."
        ),
    )


class GetComputerDetailInput(BaseModel):
    computer_id: int = Field(
        ...,
        gt=0,
        description="ID komputer di GLPI (integer > 0).",
    )


class SearchComputerByNameInput(BaseModel):
    name: str = Field(
        ...,
        description="Nama komputer yang ingin dicari di GLPI.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Jumlah maksimal hasil pencarian.",
    )


class SearchComputerInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Kata kunci pencarian bebas: bisa nama komputer, serial number, "
            "atau inventory number. Contoh: 'ABC123', 'LAPTOP-HRD', 'SN-XYZ'."
        ),
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Jumlah maksimal hasil (default 10).",
    )


class GetComputersByStatusInput(BaseModel):
    status: str = Field(
        ...,
        description=(
            "Label status yang dicari, mis: 'aktif', 'rusak', 'disposed', 'in stock'."
        ),
    )
    sample_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Jumlah item yang ditampilkan sebagai sample (default 50).",
    )


class GetComputersByLocationInput(BaseModel):
    location: str = Field(
        ...,
        description=(
            "Nama lokasi yang dicari, mis: 'lantai 3', 'gedung A', 'server room'."
        ),
    )
    sample_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Jumlah item yang ditampilkan sebagai sample (default 50).",
    )


class GetComputersByOsInput(BaseModel):
    os: str = Field(
        ...,
        description=(
            "Nama OS yang dicari, mis: 'Windows 10', 'Ubuntu', 'Windows Server'."
        ),
    )
    sample_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Jumlah item yang ditampilkan sebagai sample (default 50).",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tools
# ══════════════════════════════════════════════════════════════════════════════

class GetUserAssetsTool(BaseTool):
    """Ambil daftar komputer milik user dari GLPI."""

    name: str = "get_user_assets"
    description: str = (
        "Ambil daftar aset komputer yang DIMILIKI atau DITUGASKAN kepada user tertentu. "
        "HANYA gunakan saat user bertanya tentang komputer miliknya sendiri "
        "atau milik user spesifik lainnya. "
        "JANGAN gunakan untuk semua inventaris — gunakan get_all_computers."
    )
    args_schema: Type[BaseModel] = GetUserAssetsInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return (
                "Sistem tidak dapat menemukan aset: ID User belum terdeteksi (user_id=0). "
                "Pastikan user sudah login dengan benar atau hubungi admin IT."
            )
        logger.info("Tool Asset | user_id=%s", user_id)
        try:
            results: list[dict[str, Any]] = run_async(
                asset_repository.get_user_assets(user_id)
            )
            if not results:
                return (
                    f"User ID {user_id} tidak memiliki aset komputer yang terdaftar di GLPI."
                )

            output = f"Daftar aset komputer user ID {user_id} ({len(results)} item):\n\n"
            for idx, item in enumerate(results, 1):
                output += _fmt_computer_row(idx, item)
            return output
        except Exception as exc:
            logger.error("Asset fetch failed: %s", exc)
            return f"Gagal mengambil data aset: {exc}"


class GetAllComputersTool(BaseTool):
    """Ambil daftar komputer di GLPI beserta sample data. Gunakan hanya untuk listing, bukan counting."""

    name: str = "get_all_computers"
    description: str = (
        "Ambil daftar SEMUA komputer di inventaris GLPI beserta sample data. "
        "HANYA gunakan saat user meminta DAFTAR atau LIST komputer — bukan untuk COUNT. "
        "⛔ DILARANG KERAS menggunakan tool ini untuk pertanyaan 'berapa', 'jumlah', "
        "'total', 'summary', 'ringkasan', atau 'ada berapa' — "
        "gunakan count_all_computers untuk itu. "
        "⛔ DILARANG untuk mencari by nama/serial — gunakan search_computer. "
        "⛔ DILARANG untuk aset milik user tertentu — gunakan get_user_assets."
    )
    args_schema: Type[BaseModel] = GetAllComputersInput
    # Cache aktif: inventaris tidak berubah dalam hitungan detik; mencegah
    # agent memanggil tool ini berkali-kali dengan argumen sama dalam satu request.
    cache_function: Any = Field(default=lambda tool_name, tool_args: True)

    def _run(
        self,
        sample_size: int = 50,
        has_serial: bool = False,
        paginate: bool = True,
    ) -> str:
        logger.info(
            "Tool All Computers | sample_size=%s | has_serial=%s | paginate=%s",
            sample_size, has_serial, paginate,
        )
        try:
            result: PagedResult = run_async(
                asset_repository.get_all_computers(
                    sample_size=sample_size,
                    has_serial=has_serial,
                    paginate=paginate,
                )
            )

            if not result["items"] and result["totalcount"] == 0:
                label = "komputer dengan serial number" if has_serial else "komputer"
                return f"Tidak ada {label} ditemukan di GLPI."

            context = "komputer dengan serial number" if has_serial else "komputer"
            output = _render_paged_result(result, context=context)
            output += f"\n\n[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {result['totalcount']}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."
            return output

        except Exception as exc:
            logger.error("Computer list failed: %s", exc)
            return f"Gagal mengambil daftar komputer: {exc}"


class GetComputerDetailTool(BaseTool):
    """Ambil detail lengkap satu komputer berdasarkan ID-nya."""

    name: str = "get_computer_detail"
    description: str = (
        "Ambil detail LENGKAP satu komputer berdasarkan ID-nya, termasuk: "
        "Name, Entity, Serial Number, Inventory Number, Location, Type, Model, "
        "Manufacturer, Alternate Username, Operating System, Status, "
        "Financial/Startup Date, Comments, Documents count, dan Last Update. "
        "WAJIB dipanggil saat user meminta 'data lengkap', 'detail', atau 'info lengkap' "
        "suatu komputer — meskipun nama komputer sudah ada di riwayat percakapan."
    )
    args_schema: Type[BaseModel] = GetComputerDetailInput

    def _run(self, computer_id: int) -> str:
        try:
            comp: dict[str, Any] | None = run_async(
                asset_repository.get_computer_by_id(computer_id)
            )
            if not comp:
                return f"Komputer dengan ID {computer_id} tidak ditemukan di GLPI."
            # Gunakan formatter full-detail khusus tool ini (bukan _fmt_computer_row)
            return _fmt_computer_full_detail(comp)
        except Exception as exc:
            logger.error("Computer detail fetch failed: %s", exc)
            return f"Gagal mengambil detail komputer: {exc}"


class CountAllAssetsTool(BaseTool):
    """Hitung jumlah total SELURUH aset di GLPI (1 API call)."""

    name: str = "count_all_assets"
    description: str = (
        "Ambil TOTAL atau JUMLAH KESELURUHAN SELURUH ASET (Komputer, Monitor, Printer, Network Equipment, dll) "
        "yang ada di GLPI secara exact. "
        "Gunakan HANYA jika ditanya 'ada berapa total aset', 'jumlah aset', atau 'total aset' secara umum. "
        "Jika ditanya jumlah KOMPUTER saja, gunakan count_all_computers."
    )
    cache_function: Any = Field(default=lambda *args, **kwargs: False)

    def _run(self) -> str:
        session_id = get_session_id()
        cached = get_count_cache(session_id, "count_all_assets")
        if cached:
            logger.info("CountAllAssetsTool | cache HIT | session=%s", session_id[:20])
            return cached

        try:
            total: int = run_async(asset_repository.get_total_all_assets_count())
            total_fmt = f"{total:,}".replace(",", ".")
            result = (
                f"Total seluruh aset (termasuk Komputer, Monitor, Printer, "
                f"Network Equipment, dll) yang terdaftar di GLPI adalah "
                f"**{total_fmt} item**."
                f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
                f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} item. "
                f"DILARANG memanggil tool apapun lagi."
            )
            set_count_cache(session_id, "count_all_assets", result)
            return result
        except Exception as exc:
            logger.error("CountAllAssetsTool failed: %s", exc)
            return f"Gagal menghitung jumlah seluruh aset: {exc}"


class CountAllComputersTool(BaseTool):
    """Hitung jumlah total komputer di GLPI (cepat, 1 API call)."""

    name: str = "count_all_computers"
    description: str = (
        "Ambil TOTAL atau JUMLAH KESELURUHAN komputer yang ada di GLPI secara exact. "
        "Gunakan HANYA jika ditanya 'ada berapa', 'jumlah', atau 'total' komputer. "
        "Lebih cepat dari get_all_computers karena hanya mengambil count, bukan data."
    )
    cache_function: Any = Field(default=lambda *args, **kwargs: False)

    def _run(self) -> str:
        session_id = get_session_id()
        cached = get_count_cache(session_id, "count_all_computers")
        if cached:
            logger.info("CountAllComputersTool | cache HIT | session=%s", session_id[:20])
            return cached

        try:
            total: int = run_async(asset_repository.get_total_computers_count())
            total_fmt = f"{total:,}".replace(",", ".")
            result = (
                f"Total komputer yang terdaftar di sistem GLPI adalah "
                f"**{total_fmt} unit**."
                f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
                f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} unit. "
                f"DILARANG memanggil tool apapun lagi."
            )
            set_count_cache(session_id, "count_all_computers", result)
            return result
        except Exception as exc:
            logger.error("CountAllComputersTool failed: %s", exc)
            return f"Gagal menghitung jumlah komputer: {exc}"


class SearchComputerByNameTool(BaseTool):
    """Cari komputer di GLPI berdasarkan namanya."""

    name: str = "search_computer_by_name"
    description: str = (
        "Cari komputer di inventaris GLPI berdasarkan namanya. "
        "Gunakan saat user memberikan nama spesifik komputer. "
        "Lebih baik gunakan search_computer yang juga mencakup serial dan inventory number."
    )
    args_schema: Type[BaseModel] = SearchComputerByNameInput

    def _run(self, name: str, limit: int = 20) -> str:
        logger.info("Tool Search Computer By Name | name=%s | limit=%s", name, limit)
        try:
            results: list[dict[str, Any]] = run_async(
                asset_repository.search_computer_by_name(name, limit)
            )
            if not results:
                return f"Komputer dengan nama '{name}' tidak ditemukan di GLPI."

            output = f"Hasil pencarian nama '{name}' ({len(results)} item):\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computer search by name failed: %s", exc)
            return f"Gagal mencari komputer: {exc}"


class SearchComputerTool(BaseTool):
    """Cari komputer di GLPI berdasarkan nama, serial number, ATAU inventory number."""

    name: str = "search_computer"
    description: str = (
        "Cari komputer di GLPI menggunakan satu kata kunci yang dicocokkan secara "
        "otomatis ke TIGA field sekaligus: Nama, Serial Number, dan Inventory Number. "
        "Gunakan saat user mengetik kode/identifier yang tidak jelas field-nya. "
        "LEBIH EFISIEN dari search_computer_by_name karena satu call sudah mencakup tiga field."
    )
    args_schema: Type[BaseModel] = SearchComputerInput

    def _run(self, query: str, limit: int = 10) -> str:
        logger.info(
            "Tool Search Computer (universal) | query='%s' | limit=%s", query, limit
        )
        try:
            results: list[dict[str, Any]] = run_async(
                asset_repository.search_computer(query, limit)
            )
            if not results:
                return (
                    f"Komputer dengan kata kunci '{query}' tidak ditemukan di GLPI. "
                    "(Pencarian sudah dilakukan pada field: Nama, Serial Number, Inventory Number)"
                )

            # Deteksi field yang kemungkinan cocok untuk output yang lebih informatif
            q             = query.lower()
            likely_field  = "pencarian"
            for comp in results:
                sn  = (comp.get("serial")      or "").lower()
                inv = (comp.get("otherserial") or "").lower()
                nm  = (comp.get("name")        or "").lower()
                if sn and q in sn:
                    likely_field = "serial number"; break
                if inv and q in inv:
                    likely_field = "inventory number"; break
                if nm and q in nm:
                    likely_field = "nama"; break

            output = f"Ditemukan {len(results)} komputer dengan {likely_field} '{query}':\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computer universal search failed: %s", exc)
            return f"Gagal mencari komputer: {exc}"


class GetComputersByStatusTool(BaseTool):
    """Cari komputer di GLPI berdasarkan status aset."""

    name: str = "get_computers_by_status"
    description: str = (
        "Cari komputer di GLPI berdasarkan status aset. "
        "Menampilkan total exact + statistik distribusi jika hasil > 100. "
        "Contoh query: 'komputer aktif', 'aset rusak', 'stok tersedia'. "
        "Pencarian case-insensitive dan partial match. "
        "Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."
    )
    args_schema: Type[BaseModel] = GetComputersByStatusInput

    def _run(self, status: str, sample_size: int = 50) -> str:
        logger.info(
            "Tool Computers By Status | status='%s' | sample_size=%s", status, sample_size
        )
        try:
            result: PagedResult = run_async(
                asset_repository.get_computers_by_status(status, sample_size)
            )
            if not result["items"] and result["totalcount"] == 0:
                return f"Tidak ada komputer dengan status '{status}' ditemukan di GLPI."

            output = _render_paged_result(
                result,
                context="komputer",
                filter_label=f"dengan status '{status}'",
            )
            output += f"\n\n[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {result['totalcount']}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."
            return output
        except Exception as exc:
            logger.error("Computers by status failed: %s", exc)
            return f"Gagal mencari komputer by status: {exc}"


class GetComputersByLocationTool(BaseTool):
    """Cari komputer di GLPI berdasarkan lokasi fisiknya."""

    name: str = "get_computers_by_location"
    description: str = (
        "Cari komputer di GLPI berdasarkan lokasi fisiknya. "
        "Menampilkan total exact + statistik distribusi jika hasil > 100. "
        "Contoh query: 'komputer di lantai 2', 'aset di gedung B', 'komputer server room'. "
        "Pencarian case-insensitive dan partial match. "
        "Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."
    )
    args_schema: Type[BaseModel] = GetComputersByLocationInput

    def _run(self, location: str, sample_size: int = 50) -> str:
        logger.info(
            "Tool Computers By Location | location='%s' | sample_size=%s",
            location, sample_size,
        )
        try:
            result: PagedResult = run_async(
                asset_repository.get_computers_by_location(location, sample_size)
            )
            if not result["items"] and result["totalcount"] == 0:
                return f"Tidak ada komputer di lokasi '{location}' ditemukan di GLPI."

            output = _render_paged_result(
                result,
                context="komputer",
                filter_label=f"di lokasi '{location}'",
            )
            output += f"\n\n[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {result['totalcount']}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."
            return output
        except Exception as exc:
            logger.error("Computers by location failed: %s", exc)
            return f"Gagal mencari komputer by lokasi: {exc}"


class GetComputersByOsTool(BaseTool):
    """Cari komputer di GLPI berdasarkan sistem operasi yang terinstall."""

    name: str = "get_computers_by_os"
    description: str = (
        "Cari komputer di GLPI berdasarkan sistem operasi (OS) yang terinstall. "
        "Menampilkan total exact + statistik distribusi jika hasil > 100. "
        "Contoh query: 'komputer Windows 10', 'laptop Ubuntu', 'server Windows Server 2019'. "
        "Pencarian case-insensitive dan partial match. "
        "Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."
    )
    args_schema: Type[BaseModel] = GetComputersByOsInput

    def _run(self, os: str, sample_size: int = 50) -> str:
        logger.info(
            "Tool Computers By OS | os='%s' | sample_size=%s", os, sample_size
        )
        try:
            result: PagedResult = run_async(
                asset_repository.get_computers_by_os(os, sample_size)
            )
            if not result["items"] and result["totalcount"] == 0:
                return f"Tidak ada komputer dengan OS '{os}' ditemukan di GLPI."

            output = _render_paged_result(
                result,
                context="komputer",
                filter_label=f"dengan OS '{os}'",
            )
            output += f"\n\n[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {result['totalcount']}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."
            return output
        except Exception as exc:
            logger.error("Computers by OS failed: %s", exc)
            return f"Gagal mencari komputer by OS: {exc}"