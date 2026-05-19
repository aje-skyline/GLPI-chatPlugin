"""CrewAI tools for querying GLPI data.

Each tool is a BaseTool subclass with a typed Pydantic input schema.
Tools are called by IT Support Agent based on user intent.

FIXES v3.0:
  - Tambah tiga tool baru: GetComputersByStatusTool, GetComputersByLocationTool,
    GetComputersByOsTool — memanfaatkan fungsi client yang sudah ada tapi belum
    di-expose sebagai tool.
  - Fix GetAllComputersTool: hapus duplicate empty-check yang unreachable.
  - Fix GetContractDetailTool: output sekarang terformat (bukan raw str(dict)).
  - Fix GetCategoriesTool: output terformat, bukan raw str(list).
  - Semua tool output menggunakan format teks yang konsisten dan mudah dibaca LLM.
  - _run_async: timeout naik ke 45s untuk query besar.
"""

import asyncio
import logging
import threading
from typing import Any, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app import it_glpi_client

logger = logging.getLogger(__name__)


# ── Persistent background event loop ─────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return the global background event loop, creating it once if needed."""
    global _loop
    if _loop is not None and _loop.is_running():
        return _loop
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop
        loop = asyncio.new_event_loop()

        def _run(lp: asyncio.AbstractEventLoop) -> None:
            asyncio.set_event_loop(lp)
            lp.run_forever()

        t = threading.Thread(target=_run, args=(loop,), daemon=True, name="glpi-async-loop")
        t.start()

        import time
        deadline = time.monotonic() + 2.0
        while not loop.is_running():
            time.sleep(0.005)
            if time.monotonic() > deadline:
                raise RuntimeError("Background event loop failed to start within 2 s")

        _loop = loop
        logger.info("GLPI background async loop started (thread=%s)", t.name)
    return _loop


def _run_async(coro: Any, timeout: float = 45.0) -> Any:
    """Submit *coro* to the persistent background loop and block until done."""
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise TimeoutError(f"GLPI async call timed out after {timeout}s")


# ── Shared computer detail formatter ─────────────────────────────────────────

def _fmt_computer_row(idx: int, comp: dict[str, Any], detail: bool = False) -> str:
    """Format satu komputer menjadi baris teks yang konsisten."""
    name = comp.get("name") or "-"
    cid = comp.get("id") or "-"
    lines = [f"{idx}. **{name}** (ID: {cid})"]

    def _add(label: str, key: str) -> None:
        val = comp.get(key) or "(tidak ada)"
        lines.append(f"   {label:<18}: {val}")

    _add("Serial Number", "serial")
    _add("Inventory Number", "otherserial")
    _add("Type", "type")
    _add("Model", "model")
    _add("Status", "status")
    _add("Lokasi", "location")
    _add("User", "user")

    if comp.get("entity"):
        _add("Entity", "entity")
    if comp.get("manufacturer"):
        _add("Pabrikan", "manufacturer")
    if comp.get("os"):
        _add("OS", "os")
    if comp.get("date_mod"):
        _add("Terakhir Update", "date_mod")

    if detail:
        lines.append("   Data Finansial:")
        _add("  Tgl Beli", "buy_date")
        _add("  Tgl Pakai", "use_date")
        warranty = comp.get("warranty_duration") or "(tidak ada)"
        lines.append(f"   {'Garansi':<18}: {warranty} bulan")
        if comp.get("warranty_date"):
            _add("  Garansi Berakhir", "warranty_date")
        _add("  Nilai Aset", "value")
        _add("  Supplier", "supplier")
        contracts = comp.get("contracts") or []
        if contracts:
            lines.append("   Kontrak terkait:")
            for c in contracts:
                end = c.get("end_date") or "(tidak ada)"
                lines.append(f"     - {c.get('name', '-')} (ID: {c.get('id', '-')}) | Berakhir: {end}")

    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge Base
# ══════════════════════════════════════════════════════════════════════════════

class SearchKnowledgeBaseInput(BaseModel):
    query: str = Field(
        ...,
        description="Kata kunci pencarian artikel KB (e.g., 'reset password', 'install VPN')",
    )

class SearchKnowledgeBaseTool(BaseTool):
    """Cari artikel panduan di Knowledge Base GLPI."""
    name: str = "search_knowledge_base"
    description: str = (
        "Cari artikel panduan / FAQ di Knowledge Base GLPI berdasarkan kata kunci. "
        "Gunakan saat user bertanya cara mengatasi masalah IT, butuh panduan teknis, "
        "atau bertanya tentang prosedur/kebijakan IT."
    )
    args_schema: Type[BaseModel] = SearchKnowledgeBaseInput

    def _run(self, query: str) -> str:
        logger.info("Tool KB | query='%s'", query)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.fetch_knowbase_items(query, limit=5)
            )
            if not results:
                return "Tidak ditemukan artikel yang relevan di Knowledge Base."

            output = f"Hasil pencarian Knowledge Base untuk '{query}':\n\n"
            for idx, item in enumerate(results, 1):
                title: str = item.get("title") or "(tanpa judul)"
                answer: str = (item.get("answer") or "")[:500]
                output += f"{idx}. **{title}**\n{answer}...\n\n"
            return output
        except Exception as exc:
            logger.error("KB search failed: %s", exc)
            return f"Gagal mencari di Knowledge Base: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Assets — Computers
# ══════════════════════════════════════════════════════════════════════════════

class GetUserAssetsInput(BaseModel):
    user_id: int = Field(..., ge=0, description="ID user GLPI. Gunakan 0 jika tidak diketahui.")

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
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.get_user_assets(user_id)
            )
            if not results:
                return f"User ID {user_id} tidak memiliki aset komputer yang terdaftar di GLPI."

            output = f"Daftar aset komputer user ID {user_id} ({len(results)} item):\n\n"
            for idx, item in enumerate(results, 1):
                output += _fmt_computer_row(idx, item)
            return output
        except Exception as exc:
            logger.error("Asset fetch failed: %s", exc)
            return f"Gagal mengambil data aset: {exc}"


class GetAllComputersInput(BaseModel):
    limit: int = Field(
        default=50, ge=1, le=100000,
        description="Jumlah maksimum komputer yang dikembalikan (default 50).",
    )
    has_serial: bool = Field(
        default=False,
        description="Jika True, hanya kembalikan komputer yang memiliki serial number.",
    )

class GetAllComputersTool(BaseTool):
    """Ambil semua komputer di GLPI (untuk IT Admin)."""
    name: str = "get_all_computers"
    description: str = (
        "Ambil daftar SEMUA komputer yang terdaftar di inventaris GLPI. "
        "Gunakan untuk: menelusuri inventaris umum atau melihat daftar lengkap komputer. "
        "JANGAN gunakan untuk mencari komputer by nama/serial — gunakan search_computer. "
        "JANGAN gunakan untuk aset milik user tertentu — gunakan get_user_assets."
    )
    args_schema: Type[BaseModel] = GetAllComputersInput

    def _run(self, limit: int = 50, has_serial: bool = False) -> str:
        logger.info("Tool All Computers | limit=%s | has_serial=%s", limit, has_serial)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.get_all_computers(limit=limit, has_serial=has_serial)
            )
            if not results:
                label_empty = "komputer dengan serial number" if has_serial else "komputer"
                return f"Tidak ada {label_empty} ditemukan di GLPI."

            label = (
                f"komputer dengan serial number ({len(results)} item)"
                if has_serial
                else f"semua komputer ({len(results)} item)"
            )
            output = f"Daftar {label}:\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computer list failed: %s", exc)
            return f"Gagal mengambil daftar komputer: {exc}"


class GetComputerDetailInput(BaseModel):
    computer_id: int = Field(..., gt=0, description="ID komputer di GLPI (integer > 0).")

class GetComputerDetailTool(BaseTool):
    name: str = "get_computer_detail"
    description: str = (
        "Ambil detail LENGKAP satu komputer berdasarkan ID-nya, termasuk Type, Model, "
        "Serial Number, Lokasi, Status, data finansial, dan kontrak terkait. "
        "WAJIB dipanggil saat user meminta 'data lengkap', 'detail', atau 'info lengkap' "
        "suatu komputer — meskipun nama komputer sudah ada di riwayat percakapan."
    )
    args_schema: Type[BaseModel] = GetComputerDetailInput

    def _run(self, computer_id: int) -> str:
        try:
            comp = _run_async(it_glpi_client.get_computer_by_id(computer_id))
            if not comp:
                return f"Komputer dengan ID {computer_id} tidak ditemukan di GLPI."
            return f"Detail Komputer (ID: {computer_id}):\n\n" + _fmt_computer_row(1, comp, detail=True)
        except Exception as exc:
            return f"Gagal mengambil detail komputer: {exc}"


class CountAllComputersInput(BaseModel):
    pass

class CountAllComputersTool(BaseTool):
    name: str = "count_all_computers"
    description: str = (
        "Ambil TOTAL atau JUMLAH KESELURUHAN komputer yang ada di GLPI. "
        "Gunakan HANYA jika ditanya 'ada berapa', 'jumlah', atau 'total' komputer. "
        "Jangan gunakan jika user meminta nama atau daftar spesifik."
    )
    args_schema: Type[BaseModel] = CountAllComputersInput

    def _run(self, **kwargs) -> str:
        try:
            total = _run_async(it_glpi_client.get_total_computers_count())
            return f"Total komputer yang terdaftar di sistem GLPI adalah {total} unit."
        except Exception as exc:
            return f"Gagal menghitung jumlah komputer: {exc}"


class SearchComputerByNameInput(BaseModel):
    name: str = Field(..., description="Nama komputer yang ingin dicari di GLPI.")
    limit: int = Field(default=50, ge=1, le=200, description="Jumlah maksimal hasil pencarian.")

class SearchComputerByNameTool(BaseTool):
    name: str = "search_computer_by_name"
    description: str = (
        "Cari komputer di inventaris GLPI berdasarkan namanya. "
        "Gunakan saat user memberikan nama spesifik komputer. "
        "Lebih baik gunakan search_computer yang juga mencakup serial dan inventory number."
    )
    args_schema: Type[BaseModel] = SearchComputerByNameInput

    def _run(self, name: str, limit: int = 50) -> str:
        logger.info("Tool Search Computer By Name | name=%s | limit=%s", name, limit)
        try:
            results = _run_async(it_glpi_client.search_computer_by_name(name, limit))
            if not results:
                return f"Komputer dengan nama '{name}' tidak ditemukan di GLPI."

            output = f"Hasil pencarian nama '{name}' ({len(results)} item):\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computer search by name failed: %s", exc)
            return f"Gagal mencari komputer: {exc}"


class SearchComputerInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Kata kunci pencarian bebas: bisa nama komputer, serial number, "
            "atau inventory number. Contoh: 'ABC123', 'LAPTOP-HRD', 'SN-XYZ'."
        ),
    )
    limit: int = Field(default=10, ge=1, le=50, description="Jumlah maksimal hasil (default 10).")

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
        logger.info("Tool Search Computer (universal) | query='%s' | limit=%s", query, limit)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.search_computer(query, limit)
            )
            if not results:
                return (
                    f"Komputer dengan kata kunci '{query}' tidak ditemukan di GLPI. "
                    "(Pencarian sudah dilakukan pada field: Nama, Serial Number, Inventory Number)"
                )

            # Deteksi field yang kemungkinan cocok
            q = query.lower()
            likely_field = "pencarian"
            for comp in results:
                sn = (comp.get("serial") or "").lower()
                inv = (comp.get("otherserial") or "").lower()
                nm = (comp.get("name") or "").lower()
                if sn and q in sn:
                    likely_field = "serial number"
                    break
                if inv and q in inv:
                    likely_field = "inventory number"
                    break
                if nm and q in nm:
                    likely_field = "nama"
                    break

            output = f"Ditemukan {len(results)} komputer dengan {likely_field} '{query}':\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Universal computer search failed: %s", exc)
            return f"Gagal mencari komputer: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Filter Tools — Status, Location, OS
# ══════════════════════════════════════════════════════════════════════════════

class GetComputersByStatusInput(BaseModel):
    status: str = Field(..., description="Status komputer yang dicari, mis: 'aktif', 'rusak', 'disposed'.")
    limit: int = Field(default=50, ge=1, le=200, description="Jumlah maksimal hasil.")

class GetComputersByStatusTool(BaseTool):
    name: str = "get_computers_by_status"
    description: str = (
        "Cari komputer di GLPI yang memiliki status tertentu. "
        "Contoh query: 'komputer yang rusak', 'komputer status aktif', 'aset disposed'. "
        "Pencarian case-insensitive dan partial match."
    )
    args_schema: Type[BaseModel] = GetComputersByStatusInput

    def _run(self, status: str, limit: int = 50) -> str:
        logger.info("Tool Computers By Status | status='%s' | limit=%s", status, limit)
        try:
            results = _run_async(it_glpi_client.get_computers_by_status(status, limit))
            if not results:
                return f"Tidak ada komputer dengan status '{status}' ditemukan di GLPI."
            output = f"Komputer dengan status '{status}' ({len(results)} item):\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computers by status failed: %s", exc)
            return f"Gagal mencari komputer by status: {exc}"


class GetComputersByLocationInput(BaseModel):
    location: str = Field(..., description="Nama lokasi yang dicari, mis: 'lantai 3', 'gedung A', 'server room'.")
    limit: int = Field(default=50, ge=1, le=200, description="Jumlah maksimal hasil.")

class GetComputersByLocationTool(BaseTool):
    name: str = "get_computers_by_location"
    description: str = (
        "Cari komputer di GLPI berdasarkan lokasi fisiknya. "
        "Contoh query: 'komputer di lantai 2', 'aset di gedung B', 'komputer server room'. "
        "Pencarian case-insensitive dan partial match."
    )
    args_schema: Type[BaseModel] = GetComputersByLocationInput

    def _run(self, location: str, limit: int = 50) -> str:
        logger.info("Tool Computers By Location | location='%s' | limit=%s", location, limit)
        try:
            results = _run_async(it_glpi_client.get_computers_by_location(location, limit))
            if not results:
                return f"Tidak ada komputer di lokasi '{location}' ditemukan di GLPI."
            output = f"Komputer di lokasi '{location}' ({len(results)} item):\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computers by location failed: %s", exc)
            return f"Gagal mencari komputer by lokasi: {exc}"


class GetComputersByOsInput(BaseModel):
    os: str = Field(..., description="Nama OS yang dicari, mis: 'Windows 10', 'Ubuntu', 'Windows Server'.")
    limit: int = Field(default=50, ge=1, le=200, description="Jumlah maksimal hasil.")

class GetComputersByOsTool(BaseTool):
    name: str = "get_computers_by_os"
    description: str = (
        "Cari komputer di GLPI berdasarkan sistem operasi (OS) yang terinstall. "
        "Contoh query: 'komputer Windows 10', 'laptop Ubuntu', 'server Windows Server 2019'. "
        "Pencarian case-insensitive dan partial match."
    )
    args_schema: Type[BaseModel] = GetComputersByOsInput

    def _run(self, os: str, limit: int = 50) -> str:
        logger.info("Tool Computers By OS | os='%s' | limit=%s", os, limit)
        try:
            results = _run_async(it_glpi_client.get_computers_by_os(os, limit))
            if not results:
                return f"Tidak ada komputer dengan OS '{os}' ditemukan di GLPI."
            output = f"Komputer dengan OS '{os}' ({len(results)} item):\n\n"
            for idx, comp in enumerate(results, 1):
                output += _fmt_computer_row(idx, comp)
            return output
        except Exception as exc:
            logger.error("Computers by OS failed: %s", exc)
            return f"Gagal mencari komputer by OS: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Contracts
# ══════════════════════════════════════════════════════════════════════════════

class GetContractsInput(BaseModel):
    computer_id: int = Field(
        default=0, ge=0,
        description="ID komputer (opsional). Jika 0, ambil semua kontrak.",
    )
    active_only: bool = Field(
        default=False,
        description="Jika True, filter hanya kontrak yang masih aktif.",
    )

class GetContractsTool(BaseTool):
    name: str = "list_all_contracts"
    description: str = (
        "Ambil daftar kontrak dari GLPI. Bisa difilter berdasarkan komputer "
        "atau hanya kontrak aktif."
    )
    args_schema: Type[BaseModel] = GetContractsInput

    def _run(self, computer_id: int = 0, active_only: bool = False) -> str:
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.get_contracts(computer_id=computer_id)
            )
            if not results:
                return "Tidak ada kontrak ditemukan di GLPI."

            if active_only:
                import datetime
                today = datetime.date.today().isoformat()
                results = [
                    c for c in results
                    if not c.get("end_date") or c.get("end_date", "") >= today
                ]
                if not results:
                    return "Tidak ada kontrak aktif ditemukan."

            output = f"Daftar kontrak ({len(results)} item):\n\n"
            for c in results:
                output += (
                    f"• **{c.get('name') or '-'}** (ID: {c.get('id') or '-'})\n"
                    f"  Nomor    : {c.get('num') or '(tidak ada)'}\n"
                    f"  Supplier : {c.get('supplier') or '(tidak ada)'}\n"
                    f"  Mulai    : {c.get('begin_date') or '(tidak ada)'}\n"
                    f"  Berakhir : {c.get('end_date') or '(tidak ada)'}\n\n"
                )
            return output
        except Exception as exc:
            return f"Gagal mengambil kontrak: {exc}"


class GetContractDetailInput(BaseModel):
    contract_id: int = Field(..., gt=0, description="ID kontrak di GLPI.")

class GetContractDetailTool(BaseTool):
    name: str = "get_contract_detail"
    description: str = "Ambil detail lengkap satu kontrak berdasarkan ID-nya."
    args_schema: Type[BaseModel] = GetContractDetailInput

    def _run(self, contract_id: int) -> str:
        try:
            c = _run_async(it_glpi_client.get_contract_by_id(contract_id))
            if not c:
                return f"Kontrak dengan ID {contract_id} tidak ditemukan di GLPI."
            output = f"Detail Kontrak (ID: {contract_id}):\n\n"
            output += f"  Nama     : {c.get('name') or '-'}\n"
            output += f"  Nomor    : {c.get('num') or '(tidak ada)'}\n"
            output += f"  Supplier : {c.get('supplier') or '(tidak ada)'}\n"
            output += f"  Tipe     : {c.get('type') or '(tidak ada)'}\n"
            output += f"  Mulai    : {c.get('begin_date') or '(tidak ada)'}\n"
            output += f"  Durasi   : {c.get('duration') or '(tidak ada)'} bulan\n"
            output += f"  Berakhir : {c.get('end_date') or '(tidak ada)'}\n"
            if c.get("comment"):
                output += f"  Catatan  : {c['comment']}\n"
            return output
        except Exception as exc:
            return f"Gagal mengambil detail kontrak: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

class GetMultipleItemsInput(BaseModel):
    query: str = Field(..., description="Format input: 'Computer:1,Contract:2'")

class GetMultipleItemsTool(BaseTool):
    name: str = "get_multiple_items"
    description: str = "Ambil beberapa item GLPI sekaligus dalam satu request."
    args_schema: Type[BaseModel] = GetMultipleItemsInput

    def _run(self, query: str) -> str:
        try:
            items: list[dict[str, Any]] = []
            for part in query.split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                itemtype, items_id = part.split(":", 1)
                items.append({"itemtype": itemtype.strip(), "items_id": int(items_id.strip())})

            if not items:
                return "Format query tidak valid. Gunakan format: 'Computer:1,Contract:2'"
            results = _run_async(it_glpi_client.get_multiple_items(items))
            if not results:
                return "Data tidak ditemukan."
            # Format output sebagai teks bersih
            lines = []
            for r in results:
                lines.append(f"• {r.get('itemtype', '-')} ID {r.get('id', '-')}: {r.get('name', '-')}")
            return "Hasil:\n" + "\n".join(lines)
        except Exception as exc:
            return f"Gagal: {exc}"


class ListSearchOptionsInput(BaseModel):
    itemtype: str = Field(..., description="Contoh: 'Computer', 'Ticket'")

class ListSearchOptionsTool(BaseTool):
    name: str = "list_search_options"
    description: str = "Ambil daftar field (opsi pencarian) yang tersedia untuk tipe item GLPI."
    args_schema: Type[BaseModel] = ListSearchOptionsInput

    def _run(self, itemtype: str) -> str:
        try:
            data = _run_async(it_glpi_client.list_search_options(itemtype))
            if not data:
                return f"Tidak ada opsi pencarian untuk {itemtype}."

            output = f"Opsi pencarian {itemtype} (30 pertama):\n"
            for field_id, info in list(data.items())[:30]:
                if isinstance(info, dict):
                    output += f"  [{field_id}] {info.get('name', '-')} - {info.get('table', '-')}.{info.get('field', '-')}\n"
            return output
        except Exception as exc:
            return f"Gagal: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Tickets & User Info
# ══════════════════════════════════════════════════════════════════════════════

class GetTicketsInput(BaseModel):
    user_id: int = Field(..., ge=0, description="ID user GLPI.")

class GetTicketsTool(BaseTool):
    """Ambil daftar tiket IT milik user dari GLPI."""
    name: str = "get_user_tickets"
    description: str = (
        "Ambil daftar tiket IT support yang dimiliki user. "
        "Menampilkan status tiket, judul, tanggal update terakhir, dan ringkasan isi."
    )
    args_schema: Type[BaseModel] = GetTicketsInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return (
                "Sistem tidak dapat menampilkan tiket: ID User belum terdeteksi (user_id=0). "
                "Pastikan user sudah login dengan benar atau hubungi admin IT."
            )
        logger.info("Tool Ticket | user_id=%s", user_id)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.fetch_user_tickets(user_id)
            )
            if not results:
                return f"Tidak ada tiket ditemukan untuk user ID {user_id}."

            output = f"Daftar Tiket user ID {user_id} ({len(results)} item):\n\n"
            for t in results:
                title = t.get("title") or t.get("name") or "-"
                status = t.get("status") or "-"
                last_update = t.get("last_update") or t.get("date_mod") or "-"
                tid = t.get("id") or "-"
                content = t.get("content") or ""
                output += f"• [{status}] {title} (ID: {tid})\n"
                output += f"  Update terakhir: {last_update}\n"
                if content:
                    output += f"  Ringkasan: {content[:200]}\n"
                output += "\n"
            return output
        except Exception as exc:
            logger.error("Ticket fetch failed: %s", exc)
            return f"Gagal mengambil tiket: {exc}"


class GetUserInfoInput(BaseModel):
    user_id: int = Field(..., ge=0, description="ID user GLPI.")

class GetUserInfoTool(BaseTool):
    """Ambil detail informasi profile user."""
    name: str = "get_user_info"
    description: str = "Ambil profil informasi user, seperti nama lengkap, email, dan grup ITIL."
    args_schema: Type[BaseModel] = GetUserInfoInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return (
                "Sistem tidak dapat menampilkan profil: ID User belum terdeteksi (user_id=0). "
                "Pastikan user sudah login dengan benar atau hubungi admin IT."
            )
        logger.info("Tool User Info | user_id=%s", user_id)
        try:
            user = _run_async(it_glpi_client.fetch_user_info(user_id))
            if not user:
                return f"User dengan ID {user_id} tidak ditemukan di GLPI."

            output = f"Profil User (ID: {user_id}):\n\n"
            output += f"  Nama Lengkap : {user.get('name') or '-'}\n"
            if user.get("firstname"):
                output += f"  Nama Depan   : {user['firstname']}\n"
            if user.get("realname"):
                output += f"  Nama Belakang: {user['realname']}\n"
            output += f"  Username     : {user.get('login') or '-'}\n"
            if user.get("email"):
                output += f"  Email        : {user['email']}\n"
            if user.get("groups"):
                output += f"  Grup         : {', '.join(user['groups'])}\n"
            return output
        except Exception as exc:
            logger.error("User info failed: %s", exc)
            return f"Gagal mengambil profil user: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Categories & Suppliers
# ══════════════════════════════════════════════════════════════════════════════

class GetCategoriesInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Jumlah maksimal.")

class GetCategoriesTool(BaseTool):
    name: str = "get_itil_categories"
    description: str = "Ambil daftar kategori ITIL yang tersedia untuk pembuatan tiket."
    args_schema: Type[BaseModel] = GetCategoriesInput

    def _run(self, limit: int = 20) -> str:
        try:
            results = _run_async(it_glpi_client.fetch_itil_categories(limit=limit))
            if not results:
                return "Tidak ada kategori ITIL ditemukan."
            output = f"Daftar kategori ITIL ({len(results)} item):\n\n"
            for cat in results:
                cid = cat.get("id") or cat.get("1") or "-"
                name = cat.get("name") or cat.get("2") or "-"
                completename = cat.get("completename") or cat.get("16") or ""
                display = completename if completename and completename != name else name
                output += f"• (ID: {cid}) {display}\n"
            return output
        except Exception as exc:
            return f"Gagal mengambil kategori ITIL: {exc}"


class GetSuppliersInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Jumlah maksimal.")

class GetSuppliersTool(BaseTool):
    name: str = "get_suppliers"
    description: str = "Ambil daftar supplier/vendor yang terdaftar di GLPI."
    args_schema: Type[BaseModel] = GetSuppliersInput

    def _run(self, limit: int = 20) -> str:
        try:
            results = _run_async(it_glpi_client.fetch_suppliers(limit=limit))
            if not results:
                return "Tidak ada supplier/vendor ditemukan di GLPI."

            output = f"Daftar supplier/vendor ({len(results)} item):\n\n"
            for s in results:
                sid = s.get("id") or "-"
                name = s.get("name") or "-"
                output += f"• {name} (ID: {sid})\n"
            return output
        except Exception as exc:
            return f"Gagal mengambil supplier: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Instantiated tools — import these in it_support.py
# ══════════════════════════════════════════════════════════════════════════════

tool_search_kb                = SearchKnowledgeBaseTool()
tool_get_assets               = GetUserAssetsTool()
tool_get_all_computers        = GetAllComputersTool()
tool_get_computer_detail      = GetComputerDetailTool()
tool_get_contracts            = GetContractsTool()
tool_get_contract_detail      = GetContractDetailTool()
tool_get_multiple_items       = GetMultipleItemsTool()
tool_list_search_options      = ListSearchOptionsTool()
tool_get_tickets              = GetTicketsTool()
tool_get_user_info            = GetUserInfoTool()
tool_get_categories           = GetCategoriesTool()
tool_get_suppliers            = GetSuppliersTool()
tool_count_all_computers      = CountAllComputersTool()
tool_search_computer_by_name  = SearchComputerByNameTool()
tool_search_computer          = SearchComputerTool()
tool_get_computers_by_status  = GetComputersByStatusTool()
tool_get_computers_by_location = GetComputersByLocationTool()
tool_get_computers_by_os      = GetComputersByOsTool()