# Fix GLPI AI Total Count Hallucination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the system prompt to force the agent to use `count_all_computers` strictly for total count queries, preventing it from calling `get_all_computers` and hallucinating on truncated lists.

**Architecture:** Update `app/agents/prompt_builder.py` specifically adjusting `_LARGE_DATA_GUIDANCE` and the instructions for `get_all_computers` mapping to make the rules stricter. Add explicit mapping intent strings.

**Tech Stack:** Python

## Global Constraints
- Only edit `app/agents/prompt_builder.py`.
- No JSON/Pydantic changes needed.

---

### Task 1: Stricter Rules for Counting Computers

**Files:**
- Modify: `app/agents/prompt_builder.py`

**Interfaces:**
- Consumes: The `_LARGE_DATA_GUIDANCE` and mapping constants.
- Produces: A stricter prompt for LLMs to follow.

- [ ] **Step 1: Write minimal implementation**

Modify `_LARGE_DATA_GUIDANCE` string in `app/agents/prompt_builder.py`.
Find this section:
```python
ATURAN WAJIB:
1. "Total: X.XXX" = JUMLAH EXACT dari database — gunakan ini untuk pertanyaan count.
2. Flag ⚠️ = data ditampilkan hanyalah SAMPLE — sampaikan ke user.
3. Untuk count by filter → get_computers_by_location / get_computers_by_status.
4. JANGAN panggil get_all_computers hanya untuk count → gunakan count_all_computers.
```

Replace it with a more aggressive and strict mapping section:
```python
ATURAN WAJIB PENCARIAN ASET / KOMPUTER:
1. "Total: X.XXX" = JUMLAH EXACT dari database — gunakan ini untuk pertanyaan count.
2. Flag ⚠️ = data ditampilkan hanyalah SAMPLE — sampaikan ke user.
3. Untuk menghitung JUMLAH TOTAL KESELURUHAN (count without filter) → WAJIB gunakan tool `count_all_computers`.
4. ⛔ LARANGAN KERAS: JANGAN panggil `get_all_computers` hanya untuk mendapatkan total aset. Jika user bertanya "Ada berapa total aset/komputer", ANDA HARUS memanggil `count_all_computers`.
5. Untuk count by filter → get_computers_by_location / get_computers_by_status.

PEMETAAN INTENT KOMPUTER → TOOL:
"Ada berapa total aset GLPI saat ini"  → count_all_computers()
"Berapa jumlah komputer"               → count_all_computers()
"Tampilkan semua komputer"             → get_all_computers()
```

- [ ] **Step 2: Commit**

```bash
git add app/agents/prompt_builder.py
git commit -m "fix: enforce strict usage of count_all_computers in system prompt to prevent hallucination"
```
