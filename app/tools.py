"""CrewAI tools for querying GLPI data.

Each tool is a BaseTool subclass with a typed Pydantic input schema.
Tools are called by IT Support Agent based on user intent.

CHANGELOG (bug-fix v2.1):
  ROOT CAUSE: `asyncio.run()` creates a NEW event loop and immediately CLOSES it
  after each call. Module-level asyncio.Lock() objects in it_glpi_client.py were
  bound to the first loop ever created. On the next tool call, a second loop was
  spawned, the old locks were "orphaned", and httpx raised "Event loop is closed".
  This caused every *other* request to fail silently (odd requests worked because
  they happened to land on a fresh loop; even requests hit the closed one).

  FIX: Replace ad-hoc asyncio.run() with a single, long-lived background thread
  that runs its own event loop for the entire lifetime of the process. All tool
  calls submit coroutines to this loop via asyncio.run_coroutine_threadsafe(),
  which is thread-safe and reuses the same loop — so locks, httpx clients, and
  GLPI sessions are never orphaned.
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
# One daemon thread owns an asyncio event loop for the entire process lifetime.
# CrewAI tools (which run in FastAPI's thread-pool executor) submit coroutines
# here via asyncio.run_coroutine_threadsafe() — completely thread-safe and, most
# importantly, the loop is NEVER closed between requests.

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

        # Wait until loop is actually running before returning it.
        # run_forever() is non-blocking from caller's perspective; give it a
        # moment to enter the loop.
        import time
        deadline = time.monotonic() + 2.0
        while not loop.is_running():
            time.sleep(0.005)
            if time.monotonic() > deadline:
                raise RuntimeError("Background event loop failed to start within 2 s")

        _loop = loop
        logger.info("GLPI background async loop started (thread=%s)", t.name)
    return _loop


def _run_async(coro: Any, timeout: float = 30.0) -> Any:
    """Submit *coro* to the persistent background loop and block until done.

    This replaces the previous asyncio.run() approach.  asyncio.run() creates a
    brand-new loop, runs the coroutine, then **closes the loop** — which breaks
    any asyncio primitives (Locks, Queues, Futures) that were bound to a
    different loop.  run_coroutine_threadsafe() submits to the *existing* loop
    without ever closing it, so all shared state in it_glpi_client survives
    across calls.

    Args:
        coro   : Awaitable coroutine to run.
        timeout: Seconds to wait before raising TimeoutError (default 30 s).

    Returns:
        Whatever the coroutine returns.

    Raises:
        TimeoutError : If the coroutine does not finish within *timeout* seconds.
        Any exception raised inside the coroutine is re-raised here.
    """
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise TimeoutError(f"GLPI async call timed out after {timeout}s")


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge Base
# ══════════════════════════════════════════════════════════════════════════════

class SearchKnowledgeBaseInput(BaseModel):
    """Input schema for SearchKnowledgeBaseTool."""
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
                it_glpi_client.fetch_knowbase_items(query, limit=3)
            )
            if not results:
                return "Tidak ditemukan artikel yang relevan di Knowledge Base."

            output = "Hasil pencarian Knowledge Base:\n\n"
            for idx, item in enumerate(results, 1):
                title: str = item.get("title", "")
                answer: str = item.get("answer", "")[:400]
                output += f"{idx}. **{title}**\n{answer}...\n\n"
            return output
        except Exception as exc:
            logger.error("KB search failed: %s", exc)
            return f"Gagal mencari di Knowledge Base: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Assets — Computers
# ══════════════════════════════════════════════════════════════════════════════

class GetUserAssetsInput(BaseModel):
    """Input schema for GetUserAssetsTool."""
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI. Jika tidak tahu atau ID adalah 0, kirim 0.",
    )

class GetUserAssetsTool(BaseTool):
    """Ambil daftar komputer milik user dari GLPI."""
    name: str = "get_user_assets"
    description: str = (
        "Ambil daftar aset komputer yang DIMILIKI atau DITUGASKAN kepada user tertentu. "
        "HANYA gunakan tool ini saat user bertanya tentang komputer miliknya sendiri "
        "atau milik user spesifik lainnya. "
        "JANGAN gunakan untuk pertanyaan tentang semua inventaris — gunakan get_all_computers."
    )
    args_schema: Type[BaseModel] = GetUserAssetsInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return "Sistem: ID User Anda 0 (belum terdeteksi). Mohon tanyakan ID atau nama kepada User agar bisa mencari asetnya."

        logger.info("Tool Asset | user_id=%s", user_id)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.get_user_assets(user_id)
            )
            if not results:
                return "User tidak memiliki aset komputer yang terdaftar."

            output = "Daftar aset komputer user:\n\n"
            for idx, item in enumerate(results, 1):
                output += (
                    f"{idx}. **{item.get('name', '-')}**\n"
                    f"   ID            : {item.get('id', '-')}\n"
                    f"   Serial Number : {item.get('serial', '-') or '(tidak ada)'}\n"
                    f"   Type          : {item.get('type', '-') or '(tidak ada)'}\n"
                    f"   Model         : {item.get('model', '-') or '(tidak ada)'}\n"
                    f"   Status        : {item.get('status', '-') or '(tidak ada)'}\n\n"
                )
            return output
        except Exception as exc:
            logger.error("Asset fetch failed: %s", exc)
            return f"Gagal mengambil data aset: {exc}"


class GetAllComputersInput(BaseModel):
    """Input schema for GetAllComputersTool."""
    limit: int = Field(
        default=50, ge=1, le=200,
        description="Jumlah maksimum komputer yang dikembalikan (default 50, maks 200).",
    )
    has_serial: bool = Field(
        default=False,
        description=(
            "Jika True, hanya kembalikan komputer yang memiliki serial number. "
            "Gunakan saat user bertanya tentang komputer yang punya serial number."
        ),
    )

class GetAllComputersTool(BaseTool):
    """Ambil semua komputer di GLPI (untuk IT Admin)."""
    name: str = "get_all_computers"
    description: str = (
        "Ambil daftar SEMUA komputer yang terdaftar di inventaris GLPI (urut dari ID terkecil). "
        "Gunakan untuk: menelusuri inventaris umum, atau melihat daftar komputer tanpa filter nama. "
        "JANGAN gunakan untuk mencari komputer berdasarkan nama — gunakan search_computer_by_name. "
        "JANGAN gunakan untuk mencari aset milik user tertentu — gunakan get_user_assets."
    )
    args_schema: Type[BaseModel] = GetAllComputersInput

    def _run(self, limit: int = 50, has_serial: bool = False) -> str:
        logger.info("Tool All Computers | limit=%s | has_serial=%s", limit, has_serial)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.get_all_computers(limit=limit)
            )
            if not results:
                return "Tidak ada komputer ditemukan."

            if has_serial:
                results = [c for c in results if c.get("serial", "").strip()]

            if not results:
                return "Tidak ada komputer yang memiliki serial number."

            label = (
                f"komputer dengan serial number ({len(results)} item)"
                if has_serial
                else f"semua komputer ({len(results)} item)"
            )
            output = f"Daftar {label}:\n\n"
            for idx, comp in enumerate(results, 1):
                output += (
                    f"{idx}. **{comp.get('name', '-')}** (ID: {comp.get('id', '-')})\n"
                    f"   Serial   : {comp.get('serial', '-') or '(tidak ada)'}\n"
                    f"   Type     : {comp.get('type', '-') or '(tidak ada)'}\n"
                    f"   Model    : {comp.get('model', '-') or '(tidak ada)'}\n"
                    f"   Status   : {comp.get('status', '-') or '(tidak ada)'}\n"
                    f"   Lokasi   : {comp.get('location', '-') or '(tidak ada)'}\n"
                    f"   User     : {comp.get('user', '-') or '(tidak ada)'}\n\n"
                )
            return output
        except Exception as exc:
            logger.error("Computer list failed: %s", exc)
            return f"Gagal mengambil komputer: {exc}"


class GetComputerDetailInput(BaseModel):
    computer_id: int = Field(..., gt=0, description="ID komputer di GLPI (integer > 0).")

class GetComputerDetailTool(BaseTool):
    name: str = "get_computer_detail"
    description: str = (
        "Ambil detail LENGKAP satu komputer berdasarkan ID-nya, termasuk Type, Model, "
        "Serial Number, Lokasi, Status, data finansial, dan kontrak terkait. "
        "WAJIB dipanggil saat user meminta 'data lengkap', 'data jelas', 'data detail', "
        "'info lengkap', atau 'semua informasi' suatu komputer — "
        "MESKIPUN nama komputer sudah pernah disebut di riwayat percakapan sebelumnya."
    )
    args_schema: Type[BaseModel] = GetComputerDetailInput

    def _run(self, computer_id: int) -> str:
        try:
            comp = _run_async(it_glpi_client.get_computer_by_id(computer_id))
            if not comp:
                return f"Komputer dengan ID {computer_id} tidak ditemukan."

            output = f"Detail Komputer **{comp.get('name', '-')}** (ID: {computer_id}):\n\n"
            output += f"  Nama          : {comp.get('name', '-') or '(tidak ada)'}\n"
            output += f"  Serial Number : {comp.get('serial', '-') or '(tidak ada)'}\n"
            output += f"  Other Serial  : {comp.get('otherserial', '-') or '(tidak ada)'}\n"
            output += f"  Type          : {comp.get('type', '-') or '(tidak ada)'}\n"
            output += f"  Model         : {comp.get('model', '-') or '(tidak ada)'}\n"
            output += f"  Status        : {comp.get('status', '-') or '(tidak ada)'}\n"
            output += f"  Lokasi        : {comp.get('location', '-') or '(tidak ada)'}\n"
            output += f"  User          : {comp.get('user', '-') or '(tidak ada)'}\n"
            output += f"  Tgl Beli      : {comp.get('buy_date', '-') or '(tidak ada)'}\n"
            output += f"  Garansi       : {comp.get('warranty_duration', '-') or '(tidak ada)'}\n"
            output += f"  Nilai Aset    : {comp.get('value', '-') or '(tidak ada)'}\n"
            output += f"  Supplier      : {comp.get('supplier', '-') or '(tidak ada)'}\n"
            if comp.get("contracts"):
                output += "\nKontrak terkait:\n"
                for c in comp["contracts"]:
                    output += f"  - {c.get('name', '-')} (ID: {c.get('id', '-')})\n"
            return output
        except Exception as exc:
            return f"Gagal mengambil detail komputer: {exc}"


class CountAllComputersInput(BaseModel):
    pass

class CountAllComputersTool(BaseTool):
    name: str = "count_all_computers"
    description: str = (
        "Ambil TOTAL atau JUMLAH KESELURUHAN komputer yang ada di GLPI. "
        "Gunakan tool ini HANYA jika ditanya 'ada berapa', 'jumlah', atau 'total' komputer. "
        "Jangan gunakan tool ini jika user meminta nama atau daftar spesifik."
    )
    args_schema: Type[BaseModel] = CountAllComputersInput

    def _run(self, **kwargs)-> str:
        try:
            total = _run_async(it_glpi_client.get_total_computers_count())
            return f"Total komputer yang terdaftar di sistem adalah {total} unit."
        except Exception as exc:
            return f"Gagal menghitung jumlah komputer: {exc}"


# ── Search Computer by Name ───────────────────────────────────────────────────

class SearchComputerByNameInput(BaseModel):
    """Input schema for SearchComputerByNameTool."""
    name: str = Field(
        ...,
        description=(
            "Nama komputer (atau sebagian nama) yang ingin dicari. "
            "Contoh: 'M01463L09', 'D02028', 'LAPTOP-FINANCE'."
        ),
    )
    limit: int = Field(
        default=5, ge=1, le=20,
        description="Jumlah maksimum hasil yang dikembalikan (default 5).",
    )


class SearchComputerByNameTool(BaseTool):
    """Cari komputer spesifik berdasarkan nama menggunakan GLPI Search API."""

    name: str = "search_computer_by_name"
    description: str = (
        "Cari komputer SPESIFIK berdasarkan nama (atau sebagian nama) dari seluruh "
        "inventaris GLPI menggunakan Search API — tanpa batasan jumlah record. "
        "WAJIB gunakan tool ini saat user menyebut nama komputer tertentu "
        "(contoh: 'M01463L09', 'D02028L07'). "
        "Hasilnya mencakup: ID, Nama, Serial Number, Type (kategori hardware), "
        "Model (nama produk), Status, Lokasi, User, dan data finansial. "
        "JANGAN gunakan get_all_computers untuk mencari berdasarkan nama — "
        "get_all_computers hanya mengambil 200 record pertama dari 20.000+ data."
    )
    args_schema: Type[BaseModel] = SearchComputerByNameInput

    def _run(self, name: str, limit: int = 5) -> str:
        logger.info("Tool SearchByName | name='%s' limit=%s", name, limit)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.search_computer_by_name(name=name, limit=limit)
            )
            if not results:
                return f"Komputer dengan nama yang mengandung '{name}' tidak ditemukan di GLPI."

            output = f"Hasil pencarian komputer '{name}' ({len(results)} ditemukan):\n\n"
            for comp in results:
                output += (
                    f"**{comp.get('name', '-')}** (ID: {comp.get('id', '-')})\n"
                    f"  Serial Number : {comp.get('serial', '-') or '(tidak ada)'}\n"
                    f"  Other Serial  : {comp.get('otherserial', '-') or '(tidak ada)'}\n"
                    f"  Type          : {comp.get('type', '-') or '(tidak ada)'}\n"
                    f"  Model         : {comp.get('model', '-') or '(tidak ada)'}\n"
                    f"  Status        : {comp.get('status', '-') or '(tidak ada)'}\n"
                    f"  Lokasi        : {comp.get('location', '-') or '(tidak ada)'}\n"
                    f"  User          : {comp.get('user', '-') or '(tidak ada)'}\n"
                    f"  Tgl Beli      : {comp.get('buy_date', '-') or '(tidak ada)'}\n"
                    f"  Garansi       : {comp.get('warranty_duration', '-') or '(tidak ada)'}\n"
                    f"  Nilai Aset    : {comp.get('value', '-') or '(tidak ada)'}\n"
                    f"  Supplier      : {comp.get('supplier', '-') or '(tidak ada)'}\n"
                )
                if comp.get("contracts"):
                    output += "  Kontrak       :\n"
                    for c in comp["contracts"]:
                        output += f"    - {c.get('name', '-')} (ID: {c.get('id', '-')})\n"
                output += "\n"
            return output
        except Exception as exc:
            logger.error("SearchComputerByName failed: %s", exc)
            return f"Gagal mencari komputer '{name}': {exc}"

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
                return "Tidak ada kontrak ditemukan."

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
                    f"• **{c.get('name', '-')}** (ID: {c.get('id', '-')})\n"
                    f"  Nomor   : {c.get('num', '-') or '(tidak ada)'}\n"
                    f"  Supplier: {c.get('supplier', '-') or '(tidak ada)'}\n"
                    f"  Mulai   : {c.get('begin_date', '-') or '(tidak ada)'}\n"
                    f"  Berakhir: {c.get('end_date', '-') or '(tidak ada)'}\n\n"
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
            comp = _run_async(it_glpi_client.get_contract_by_id(contract_id))
            return str(comp) if comp else f"Kontrak ID {contract_id} tidak ditemukan."
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
                return "Format query tidak valid."
            results = _run_async(it_glpi_client.get_multiple_items(items))
            return str(results) if results else "Data tidak ditemukan."
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

            output = f"Opsi pencarian {itemtype}:\n"
            for field_id, info in list(data.items())[:30]:
                if isinstance(info, dict):
                    output += f" [{field_id}] {info.get('name', '-')} - {info.get('table', '-')}\n"
            return output
        except Exception as exc:
            return f"Gagal: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Tickets & User Info
# ══════════════════════════════════════════════════════════════════════════════

class GetTicketsInput(BaseModel):
    """Input schema for GetTicketsTool."""
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI. Jika tidak tahu atau ID adalah 0, kirim 0.",
    )

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
            return "Sistem: ID User Anda 0 (belum terdeteksi). Mohon tanyakan ID atau nama kepada User agar bisa mencari tiketnya."

        logger.info("Tool Ticket | user_id=%s", user_id)
        try:
            results: list[dict[str, Any]] = _run_async(
                it_glpi_client.fetch_user_tickets(user_id)
            )
            if not results:
                return "Tidak ada tiket ditemukan untuk user ini."

            output = f"Daftar Tiket ({len(results)} item):\n"
            for t in results:
                output += (
                    f"• [{t.get('status', '-')}] {t.get('name', '-')} (ID: {t.get('id', '-')})\n"
                    f"  Update: {t.get('date_mod', '-')}\n"
                )
            return output
        except Exception as exc:
            logger.error("Ticket fetch failed: %s", exc)
            return f"Gagal mengambil tiket: {exc}"


class GetUserInfoInput(BaseModel):
    """Input schema for GetUserInfoTool."""
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI. Jika tidak tahu atau ID adalah 0, kirim 0.",
    )

class GetUserInfoTool(BaseTool):
    """Ambil detail informasi profile user."""
    name: str = "get_user_info"
    description: str = "Ambil profil informasi user, seperti nama lengkap, email, dan grup ITIL."
    args_schema: Type[BaseModel] = GetUserInfoInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return "Sistem: ID User Anda 0 (belum terdeteksi). Mohon tanyakan ID atau nama kepada User agar bisa mencari profilnya."

        logger.info("Tool User Info | user_id=%s", user_id)
        try:
            user = _run_async(it_glpi_client.fetch_user_info(user_id))
            if not user:
                return f"User dengan ID {user_id} tidak ditemukan."

            output = f"Profil User (ID: {user_id}):\n"
            output += f"• Nama  : {user.get('name', '-')}\n"
            if user.get("email"):
                output += f"• Email : {user.get('email', '-')}\n"
            if user.get("groups"):
                output += f"• Grup  : {', '.join(user['groups'])}\n"
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
    description: str = "Ambil daftar kategori ITIL."
    args_schema: Type[BaseModel] = GetCategoriesInput

    def _run(self, limit: int = 20) -> str:
        try:
            results = _run_async(it_glpi_client.fetch_itil_categories(limit=limit))
            return str(results) if results else "Tidak ada kategori."
        except Exception as exc:
            return f"Gagal: {exc}"


class GetSuppliersInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Jumlah maksimal.")

class GetSuppliersTool(BaseTool):
    name: str = "get_suppliers"
    description: str = "Ambil daftar supplier/vendor."
    args_schema: Type[BaseModel] = GetSuppliersInput

    def _run(self, limit: int = 20) -> str:
        try:
            results = _run_async(it_glpi_client.fetch_suppliers(limit=limit))
            if not results:
                return "Tidak ada supplier ditemukan."

            output = "Daftar supplier/vendor:\n\n"
            for s in results:
                output += f"• {s.get('name', '-')} (ID: {s.get('id', '-')})\n"
            return output
        except Exception as exc:
            return f"Gagal: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Instantiated tools — import these in it_support.py
# ══════════════════════════════════════════════════════════════════════════════

tool_search_kb           = SearchKnowledgeBaseTool()
tool_get_assets          = GetUserAssetsTool()
tool_get_all_computers   = GetAllComputersTool()
tool_get_computer_detail = GetComputerDetailTool()
tool_get_contracts       = GetContractsTool()
tool_get_contract_detail = GetContractDetailTool()
tool_get_multiple_items  = GetMultipleItemsTool()
tool_list_search_options = ListSearchOptionsTool()
tool_get_tickets         = GetTicketsTool()
tool_get_user_info       = GetUserInfoTool()
tool_get_categories      = GetCategoriesTool()
tool_get_suppliers       = GetSuppliersTool()
tool_count_all_computers  = CountAllComputersTool()