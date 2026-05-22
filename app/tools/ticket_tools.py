"""app/tools/ticket_tools.py — Ticket, Knowledge Base, User Info & Utility Tools.

Berisi CrewAI Tool yang tidak masuk ke domain computer, supplier, atau contract:

  Knowledge Base:
    - SearchKnowledgeBaseTool  (search_knowledge_base)

  Tickets & User:
    - GetTicketsTool           (get_user_tickets)
    - GetUserInfoTool          (get_user_info)

  Utilities:
    - GetMultipleItemsTool     (get_multiple_items)
    - ListSearchOptionsTool    (list_search_options)
    - GetCategoriesTool        (get_itil_categories)

ATURAN ARSITEKTUR:
  - Pengambilan data HANYA melalui app.repository.* (ticket_repository /
    utility_repository).
  - Tool kontrak (GetContractsTool, GetContractDetailTool) telah dipindahkan
    ke app.tools.contract_tools sesuai Clean Architecture — domain terpisah.
  - Eksekusi async HANYA melalui app.infrastructure.async_runner.run_async.
  - Formatting output dilakukan inline di sini (data cukup sederhana, tidak
    memerlukan formatter khusus yang perlu di-share).
  - Tidak boleh ada import dari app.it_glpi_client secara langsung.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.async_runner import run_async
from app.repository import ticket_repository, utility_repository

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Input Schemas
# ══════════════════════════════════════════════════════════════════════════════

class SearchKnowledgeBaseInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Kata kunci pencarian artikel KB (e.g., 'reset password', 'install VPN')"
        ),
    )


class GetTicketsInput(BaseModel):
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI.",
    )


class GetUserInfoInput(BaseModel):
    user_id: int = Field(
        ...,
        ge=0,
        description="ID user GLPI.",
    )


class GetMultipleItemsInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Format input: 'Computer:1,Contract:2' — "
            "itemtype dan items_id dipisah titik dua, antar item dipisah koma."
        ),
    )


class ListSearchOptionsInput(BaseModel):
    itemtype: str = Field(
        ...,
        description="Contoh: 'Computer', 'Ticket'",
    )


class GetCategoriesInput(BaseModel):
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Jumlah maksimal kategori yang dikembalikan.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge Base
# ══════════════════════════════════════════════════════════════════════════════

class SearchKnowledgeBaseTool(BaseTool):
    """Cari artikel panduan di Knowledge Base GLPI."""

    name: str = "search_knowledge_base"
    description: str = (
        "Cari artikel panduan / FAQ di Knowledge Base GLPI berdasarkan kata kunci. "
        "Gunakan saat user bertanya cara mengatasi masalah IT, butuh panduan teknis, "
        "atau bertanya tentang prosedur/kebijakan IT."
    )
    args_schema: Type[BaseModel] = SearchKnowledgeBaseInput
    # Cache aktif: hasil KB jarang berubah dalam satu sesi — aman di-cache
    # per kombinasi argumen oleh CrewAI agar tool yang sama tidak dipanggil
    # dua kali dengan query identik dalam satu agent loop.
    cache_function: Any = Field(default=lambda tool_name, tool_args: True)

    def _run(self, query: str) -> str:
        logger.info("Tool KB | query='%s'", query)
        try:
            results: list[dict[str, Any]] = run_async(
                ticket_repository.fetch_knowbase_items(query, limit=5)
            )
            if not results:
                return "Tidak ditemukan artikel yang relevan di Knowledge Base."

            output = f"Hasil pencarian Knowledge Base untuk '{query}':\n\n"
            for idx, item in enumerate(results, 1):
                title:  str = item.get("title") or "(tanpa judul)"
                answer: str = (item.get("answer") or "")[:500]
                output += f"{idx}. **{title}**\n{answer}...\n\n"
            return output
        except Exception as exc:
            logger.error("KB search failed: %s", exc)
            return f"Gagal mencari di Knowledge Base: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Tickets & User Info
# ══════════════════════════════════════════════════════════════════════════════

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
            results: list[dict[str, Any]] = run_async(
                ticket_repository.fetch_user_tickets(user_id)
            )
            if not results:
                return f"Tidak ada tiket ditemukan untuk user ID {user_id}."

            output = f"Daftar Tiket user ID {user_id} ({len(results)} item):\n\n"
            for t in results:
                title       = t.get("title")       or t.get("name")     or "-"
                status      = t.get("status")       or "-"
                last_update = t.get("last_update")  or t.get("date_mod") or "-"
                tid         = t.get("id")            or "-"
                content     = t.get("content")       or ""
                output += f"• [{status}] {title} (ID: {tid})\n"
                output += f"  Update terakhir: {last_update}\n"
                if content:
                    output += f"  Ringkasan: {content[:200]}\n"
                output += "\n"
            return output
        except Exception as exc:
            logger.error("Ticket fetch failed: %s", exc)
            return f"Gagal mengambil tiket: {exc}"


class GetUserInfoTool(BaseTool):
    """Ambil detail informasi profil user dari GLPI."""

    name: str = "get_user_info"
    description: str = (
        "Ambil profil informasi user, seperti nama lengkap, email, dan grup ITIL."
    )
    args_schema: Type[BaseModel] = GetUserInfoInput

    def _run(self, user_id: int) -> str:
        if user_id <= 0:
            return (
                "Sistem tidak dapat menampilkan profil: ID User belum terdeteksi (user_id=0). "
                "Pastikan user sudah login dengan benar atau hubungi admin IT."
            )
        logger.info("Tool User Info | user_id=%s", user_id)
        try:
            user: dict[str, Any] | None = run_async(
                ticket_repository.fetch_user_info(user_id)
            )
            if not user:
                return f"User dengan ID {user_id} tidak ditemukan di GLPI."

            output  = f"Profil User (ID: {user_id}):\n\n"
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
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

class GetMultipleItemsTool(BaseTool):
    """Ambil beberapa item GLPI sekaligus dalam satu request."""

    name: str = "get_multiple_items"
    description: str = (
        "Ambil beberapa item GLPI sekaligus dalam satu request. "
        "Format input: 'Computer:1,Contract:2' (itemtype:id, dipisah koma)."
    )
    args_schema: Type[BaseModel] = GetMultipleItemsInput

    def _run(self, query: str) -> str:
        try:
            items: list[dict[str, Any]] = []
            for part in query.split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                itemtype, items_id = part.split(":", 1)
                items.append({
                    "itemtype": itemtype.strip(),
                    "items_id": int(items_id.strip()),
                })

            if not items:
                return "Format query tidak valid. Gunakan format: 'Computer:1,Contract:2'"

            results: list[dict[str, Any]] = run_async(
                utility_repository.get_multiple_items(items)
            )
            if not results:
                return "Data tidak ditemukan."

            lines = [
                f"• {r.get('itemtype', '-')} ID {r.get('id', '-')}: {r.get('name', '-')}"
                for r in results
            ]
            return "Hasil:\n" + "\n".join(lines)
        except Exception as exc:
            logger.error("GetMultipleItemsTool failed: %s", exc)
            return f"Gagal: {exc}"


class ListSearchOptionsTool(BaseTool):
    """Ambil daftar field pencarian yang tersedia untuk tipe item GLPI."""

    name: str = "list_search_options"
    description: str = (
        "Ambil daftar field (opsi pencarian) yang tersedia untuk tipe item GLPI. "
        "Berguna untuk mengetahui field apa saja yang bisa difilter atau dicari."
    )
    args_schema: Type[BaseModel] = ListSearchOptionsInput
    # Cache aktif: search options statis per GLPI version — tidak perlu re-fetch.
    cache_function: Any = Field(default=lambda tool_name, tool_args: True)

    def _run(self, itemtype: str) -> str:
        try:
            data: dict[str, Any] = run_async(
                utility_repository.list_search_options(itemtype)
            )
            if not data:
                return f"Tidak ada opsi pencarian untuk {itemtype}."

            output = f"Opsi pencarian {itemtype} (30 pertama):\n"
            for field_id, info in list(data.items())[:30]:
                if isinstance(info, dict):
                    output += (
                        f"  [{field_id}] {info.get('name', '-')} - "
                        f"{info.get('table', '-')}.{info.get('field', '-')}\n"
                    )
            return output
        except Exception as exc:
            logger.error("ListSearchOptionsTool failed: %s", exc)
            return f"Gagal: {exc}"


class GetCategoriesTool(BaseTool):
    """Ambil daftar kategori ITIL dari GLPI."""

    name: str = "get_itil_categories"
    description: str = (
        "Ambil daftar kategori ITIL yang tersedia untuk pembuatan tiket."
    )
    args_schema: Type[BaseModel] = GetCategoriesInput
    # Cache aktif: kategori ITIL sangat jarang berubah — safe to cache per session.
    cache_function: Any = Field(default=lambda tool_name, tool_args: True)

    def _run(self, limit: int = 20) -> str:
        try:
            results: list[dict[str, Any]] = run_async(
                ticket_repository.fetch_itil_categories(limit=limit)
            )
            if not results:
                return "Tidak ada kategori ITIL ditemukan."

            output = f"Daftar kategori ITIL ({len(results)} item):\n\n"
            for cat in results:
                cid          = cat.get("id")           or cat.get("1")  or "-"
                name         = cat.get("name")          or cat.get("2")  or "-"
                completename = cat.get("completename")  or cat.get("16") or ""
                display      = (
                    completename
                    if completename and completename != name
                    else name
                )
                output += f"• (ID: {cid}) {display}\n"
            return output
        except Exception as exc:
            logger.error("GetCategoriesTool failed: %s", exc)
            return f"Gagal mengambil kategori ITIL: {exc}"