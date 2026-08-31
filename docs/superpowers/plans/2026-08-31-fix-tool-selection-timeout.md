# Fix Tool Selection & Timeout Prevention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cegah timeout akibat model memilih `get_all_computers` (tool berat ~26 detik) saat intent user sebenarnya adalah count/summary yang seharusnya menggunakan `count_all_computers` (1 API call, ~1 detik).

**Architecture:** Tiga perubahan terisolasi di `app/tools/computer_tools.py`: (1) hapus field `call_id` dummy dari schema count tools, (2) ubah `_run()` count tools agar tidak menerima parameter apapun, (3) perkuat description `get_all_computers` dengan larangan eksplisit untuk intent count/summary.

**Tech Stack:** Python 3.12+, CrewAI, Pydantic v2, FastAPI

## Global Constraints

- File target: `app/tools/computer_tools.py` — tidak ada file lain yang perlu diubah
- Tidak boleh mengubah nama tool (name: str) — breaking change di prompt
- Tidak boleh mengubah interface publik `_run()` untuk tool selain count tools
- Backward compatible: tool tetap bisa dipanggil tanpa args
- Python 3.12+, Pydantic v2 semantics

---

### Task 1: Hapus `call_id` field & simplify schema count tools

**Files:**
- Modify: `app/tools/computer_tools.py:87-92`

**Interfaces:**
- Consumes: `CountAllComputersInput`, `CountAllAssetsInput` (Pydantic BaseModel)
- Produces: Kedua class dihapus sepenuhnya; `args_schema` tidak lagi di-set di tool class

- [ ] **Step 1: Hapus `CountAllComputersInput` dan `CountAllAssetsInput` dari `computer_tools.py`**

Cari baris 87-92:
```python
class CountAllComputersInput(BaseModel):
    call_id: str = Field(default="", exclude=True)

class CountAllAssetsInput(BaseModel):
    call_id: str = Field(default="", exclude=True)
```

Hapus kedua class tersebut seluruhnya.

- [ ] **Step 2: Hapus `args_schema` dari `CountAllComputersTool` dan `CountAllAssetsTool`**

Di `CountAllAssetsTool` (sekitar baris 289-299), hapus baris:
```python
    args_schema: Type[BaseModel] = CountAllAssetsInput
```

Di `CountAllComputersTool` (sekitar baris 327-336), hapus baris:
```python
    args_schema: Type[BaseModel] = CountAllComputersInput
```

- [ ] **Step 3: Ubah signature `_run()` keduanya — hilangkan `**kwargs`**

`CountAllAssetsTool._run()` dari:
```python
    def _run(self, **kwargs: Any) -> str:
```
Menjadi:
```python
    def _run(self) -> str:
```

`CountAllComputersTool._run()` dari:
```python
    def _run(self, **kwargs: Any) -> str:
```
Menjadi:
```python
    def _run(self) -> str:
```

- [ ] **Step 4: Hapus import yang tidak lagi dipakai jika ada**

Cek apakah `CountAllComputersInput` dan `CountAllAssetsInput` diimport di tempat lain:
```bash
grep -r "CountAllComputersInput\|CountAllAssetsInput" app/
```
Jika tidak ada hasil selain definisi yang sudah dihapus, tidak ada aksi tambahan.

Cek apakah `Field` masih dipakai di file (untuk schema lain yang masih ada):
```bash
grep "Field(" app/tools/computer_tools.py | head -5
```
Jika masih ada `Field(` → `Field` import tetap dipertahankan.

- [ ] **Step 5: Verifikasi server bisa start**

```bash
cd /home/ariel/projects/chatbot-fastapi && uv run python -c "from app.tools.computer_tools import CountAllComputersTool, CountAllAssetsTool; t1=CountAllComputersTool(); t2=CountAllAssetsTool(); print('OK', t1.name, t2.name)"
```

Expected output:
```
OK count_all_computers count_all_assets
```

- [ ] **Step 6: Commit**

```bash
git add app/tools/computer_tools.py
git commit -m "fix(tools): hapus call_id dummy field & **kwargs dari count tools

CountAllComputersInput dan CountAllAssetsInput hanya berisi call_id dummy
yang tidak digunakan. Schema kosong membuat model (minimax dll) kirim
JSON array invalid saat tool dipanggil, menyebabkan fallback ke
get_all_computers yang berat (~26 detik) dan timeout.

Solusi: hapus kedua Input class, hapus args_schema, ubah _run() tanpa
parameter — tool kini tidak menerima args apapun dari model."
```

---

### Task 2: Perkuat description `get_all_computers` dengan larangan count/summary

**Files:**
- Modify: `app/tools/computer_tools.py` — `GetAllComputersTool.description`

**Interfaces:**
- Consumes: tidak ada
- Produces: `GetAllComputersTool.description` (str) — dipakai CrewAI untuk tool routing

- [ ] **Step 1: Ubah description `GetAllComputersTool`**

Cari description saat ini (sekitar baris 214-222):
```python
    description: str = (
        "Ambil daftar SEMUA komputer di inventaris GLPI. "
        "Selalu mengembalikan JUMLAH EXACT total komputer (totalcount dari API), "
        "plus summary statistik (distribusi status/lokasi/OS) jika data > 100, "
        "plus sample data sebagai representasi. "
        "JANGAN gunakan untuk mencari by nama/serial — gunakan search_computer. "
        "JANGAN gunakan untuk aset milik user tertentu — gunakan get_user_assets. "
        "Daftar/cari item di GLPI. ⛔ DILARANG KERAS menggunakan tool ini hanya untuk menghitung total/jumlah item! Jika user bertanya 'ada berapa' atau 'total', Anda WAJIB menggunakan tool count_*."
    )
```

Ganti dengan:
```python
    description: str = (
        "Ambil daftar SEMUA komputer di inventaris GLPI beserta sample data. "
        "HANYA gunakan saat user meminta DAFTAR atau LIST komputer — bukan untuk COUNT. "
        "⛔ DILARANG KERAS menggunakan tool ini untuk pertanyaan 'berapa', 'jumlah', "
        "'total', 'summary', 'ringkasan', atau 'ada berapa' — "
        "gunakan count_all_computers untuk itu. "
        "⛔ DILARANG untuk mencari by nama/serial — gunakan search_computer. "
        "⛔ DILARANG untuk aset milik user tertentu — gunakan get_user_assets."
    )
```

- [ ] **Step 2: Verifikasi description tersimpan benar**

```bash
cd /home/ariel/projects/chatbot-fastapi && uv run python -c "
from app.tools.computer_tools import GetAllComputersTool
t = GetAllComputersTool()
print(t.description)
"
```

Expected: description baru tampil, mengandung kata "DILARANG KERAS" dan "count_all_computers".

- [ ] **Step 3: Verifikasi semua tool masih bisa diimport dari registry**

```bash
cd /home/ariel/projects/chatbot-fastapi && uv run python -c "
from app.tools import (
    tool_get_all_computers,
    tool_count_all_computers,
    tool_count_all_assets,
)
print('get_all_computers:', tool_get_all_computers.name)
print('count_all_computers:', tool_count_all_computers.name)
print('count_all_assets:', tool_count_all_assets.name)
print('ALL OK')
"
```

Expected:
```
get_all_computers: get_all_computers
count_all_computers: count_all_computers
count_all_assets: count_all_assets
ALL OK
```

- [ ] **Step 4: Commit**

```bash
git add app/tools/computer_tools.py
git commit -m "fix(tools): perkuat description get_all_computers — larang intent count/summary

Model (minimax dll) salah pilih get_all_computers (~26 detik, fetch 500 items)
saat user bertanya 'summary' atau 'berapa'. Penyebab: description lama menyebut
'mengembalikan JUMLAH EXACT' sehingga model pikir tool ini cocok untuk count.

Solusi: rewrite description dengan larangan eksplisit untuk intent count/summary/
ringkasan/berapa — arahkan ke count_all_computers."
```

