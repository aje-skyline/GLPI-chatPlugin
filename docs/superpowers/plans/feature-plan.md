# Implementation Plan: GLPI Chatbot Data Inconsistency & Sub-entity Scope Fix

## Global Constraints
- Target codebase: `chatbot-fastapi`
- DO NOT add `countonly="true"` globally. Only put it inside explicit count endpoints.
- DO NOT use any hallucinated variables, all references must be strictly from existing code patterns.
- Code should be clean and pass standard linters/checkers if available.

## Tasks

### Task 1: Fix Repository base_params
- Files to modify:
  - `app/repository/asset_repository.py`
  - `app/repository/contract_repository.py`
  - `app/repository/supplier_repository.py`
  - `app/repository/ticket_repository.py`
  - `app/repository/utility_repository.py`
- Description: Ensure every GLPI `/search/*` API call includes `"is_recursive": "true"` inside its `base_params` or `params` dictionary. Remove any globally placed `"countonly": "true"` if it exists outside of specific count functions. Keep `countonly="true"` exclusively for functions like `count_suppliers()`, `get_total_computers_count()`, etc.

### Task 2: Enhance Tool Listing Prompt & Smart Pagination Notice
- Files to modify:
  - `app/tools/computer_tools.py`
  - `app/tools/supplier_tools.py`
  - `app/tools/contract_tools.py`
- Description: Update the Tool Description for array-returning search tools (e.g., `get_all_computers`, `get_suppliers`). Add this exact negative constraint to the description: `"Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."`. Modify the return payload of these functions to include the instruction: `"[INSTRUKSI SISTEM]: Data di atas adalah SAMPLE. Total exact di database adalah {totalcount}. Tulis Final Answer langsung dari angka total ini dan JANGAN hitung jumlah baris di atas."`

### Task 3: Update Explicit Intent Mapping in Prompt Builder
- File to modify: `app/agents/prompt_builder.py`
- Description: Update the system prompt configuration to explicitly map intents. Find the system prompt section (likely around `_LARGE_DATA_GUIDANCE` or `_SUPPLIER_TOOL_GUIDANCE`) and inject:
  ```text
  PEMETAAN INTENT → TOOL WAJIB:
  "Berapa total / jumlah X?"    → WAJIB panggil tool count_X()
  "Daftarkan / tampilkan X?"    → Panggil tool get_X()
  ```
