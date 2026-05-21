"""app/tools/__init__.py — Tool Registry.

File ini adalah satu-satunya tempat di mana semua class tool di-*instantiate*.
Konsumer (it_support.py, crew_services.py, dsb.) cukup mengimpor instance
dari sini — tidak perlu tahu di file mana class-nya berada.

Pola penamaan instance:
  tool_<snake_case_dari_tool_name_crewai>

Contoh pemakaian di it_support.py:
    from app.tools import (
        tool_search_kb,
        tool_get_all_computers,
        tool_get_suppliers,
        tool_count_suppliers,
        # ... dst.
    )

CATATAN UNTUK PEMELIHARAAN:
  - Jika menambah Tool baru, daftarkan instance-nya di sini dan tambahkan
    ke __all__ agar mudah di-discover.
  - Urutan impor mengikuti domain: computer → supplier → ticket/utility.
"""

from __future__ import annotations

# ── Computer domain ──────────────────────────────────────────────────────────
from app.tools.computer_tools import (
    CountAllComputersTool,
    GetAllComputersTool,
    GetComputerDetailTool,
    GetComputersByLocationTool,
    GetComputersByOsTool,
    GetComputersByStatusTool,
    GetUserAssetsTool,
    SearchComputerByNameTool,
    SearchComputerTool,
)

# ── Supplier domain ──────────────────────────────────────────────────────────
from app.tools.supplier_tools import (
    CountSuppliersTool,
    SearchSuppliersTool,
)

# ── Ticket / KB / Contract / Utility domain ──────────────────────────────────
from app.tools.ticket_tools import (
    GetCategoriesTool,
    GetContractDetailTool,
    GetContractsTool,
    GetMultipleItemsTool,
    GetTicketsTool,
    GetUserInfoTool,
    ListSearchOptionsTool,
    SearchKnowledgeBaseTool,
)

# ════════════════════════════════════════════════════════════════════════════
# Instantiated tool singletons
# Semua instance dibuat SEKALI di sini (module-level singleton).
# CrewAI menggunakan referensi object ini — jangan instantiate ulang di tempat lain.
# ════════════════════════════════════════════════════════════════════════════

# Knowledge Base
tool_search_kb: SearchKnowledgeBaseTool = SearchKnowledgeBaseTool()

# Computer — listing & counting
tool_get_assets:                GetUserAssetsTool          = GetUserAssetsTool()
tool_get_all_computers:         GetAllComputersTool        = GetAllComputersTool()
tool_get_computer_detail:       GetComputerDetailTool      = GetComputerDetailTool()
tool_count_all_computers:       CountAllComputersTool      = CountAllComputersTool()

# Computer — searching
tool_search_computer_by_name:   SearchComputerByNameTool   = SearchComputerByNameTool()
tool_search_computer:           SearchComputerTool         = SearchComputerTool()

# Computer — filtered by attribute
tool_get_computers_by_status:   GetComputersByStatusTool   = GetComputersByStatusTool()
tool_get_computers_by_location: GetComputersByLocationTool = GetComputersByLocationTool()
tool_get_computers_by_os:       GetComputersByOsTool       = GetComputersByOsTool()

# Supplier
tool_get_suppliers:             SearchSuppliersTool        = SearchSuppliersTool()
tool_count_suppliers:           CountSuppliersTool         = CountSuppliersTool()

# Contracts
tool_get_contracts:             GetContractsTool           = GetContractsTool()
tool_get_contract_detail:       GetContractDetailTool      = GetContractDetailTool()

# Tickets & User
tool_get_tickets:               GetTicketsTool             = GetTicketsTool()
tool_get_user_info:             GetUserInfoTool            = GetUserInfoTool()

# Categories & Utilities
tool_get_categories:            GetCategoriesTool          = GetCategoriesTool()
tool_get_multiple_items:        GetMultipleItemsTool       = GetMultipleItemsTool()
tool_list_search_options:       ListSearchOptionsTool      = ListSearchOptionsTool()

# ════════════════════════════════════════════════════════════════════════════
# Public API — batas explicit apa yang boleh diimpor dari package ini.
# ════════════════════════════════════════════════════════════════════════════

__all__ = [
    # ── instances (gunakan ini di it_support.py / crew_services.py) ──────
    "tool_search_kb",
    "tool_get_assets",
    "tool_get_all_computers",
    "tool_get_computer_detail",
    "tool_count_all_computers",
    "tool_search_computer_by_name",
    "tool_search_computer",
    "tool_get_computers_by_status",
    "tool_get_computers_by_location",
    "tool_get_computers_by_os",
    "tool_get_suppliers",
    "tool_count_suppliers",
    "tool_get_contracts",
    "tool_get_contract_detail",
    "tool_get_tickets",
    "tool_get_user_info",
    "tool_get_categories",
    "tool_get_multiple_items",
    "tool_list_search_options",
    # ── classes (export untuk testing / subclassing jika dibutuhkan) ──────
    "GetUserAssetsTool",
    "GetAllComputersTool",
    "GetComputerDetailTool",
    "CountAllComputersTool",
    "SearchComputerByNameTool",
    "SearchComputerTool",
    "GetComputersByStatusTool",
    "GetComputersByLocationTool",
    "GetComputersByOsTool",
    "SearchSuppliersTool",
    "CountSuppliersTool",
    "GetContractsTool",
    "GetContractDetailTool",
    "GetTicketsTool",
    "GetUserInfoTool",
    "GetCategoriesTool",
    "GetMultipleItemsTool",
    "ListSearchOptionsTool",
    "SearchKnowledgeBaseTool",
]