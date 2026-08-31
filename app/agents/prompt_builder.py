"""app/agents/prompt_builder.py — Prompt & Task Description Builder.

Lapisan ini HANYA bertugas merangkai string/prompt yang akan dikirim ke LLM
sebagai task description CrewAI.

TANGGUNG JAWAB FILE INI:
  1. _format_history()         — merangkai riwayat percakapan menjadi blok konteks.
  2. _build_task_description() — menyatukan semua blok (konteks, history, panduan,
                                  pertanyaan user) menjadi satu task description final.
  3. _compress_for_history()   — meringkas jawaban panjang sebelum disimpan di sesi.

ATURAN KERAS:
  - Tidak boleh melakukan I/O, HTTP call, atau import dari lapisan infra/repo.
  - Tidak boleh melakukan logging ke file/stream (gunakan return value saja).
  - Semua fungsi bersifat pure: input string/list → output string.

CHANGELOG:
  v1.0 — Dipecah dari crew_services.py (Tahap 4 Clean Architecture).
          Memindahkan _HISTORY_WINDOW, _LARGE_DATA_GUIDANCE,
          _SUPPLIER_TOOL_GUIDANCE, _format_history(), _build_task_description(),
          _MAX_STORED_ANSWER_LEN, dan _compress_for_history().
  v1.1 — Tambah _CONTRACT_TOOL_GUIDANCE untuk panduan penggunaan tool kontrak.
          Disuntikkan ke _build_task_description agar Agent tahu kapan dan
          bagaimana harus menggunakan count_contracts / list_all_contracts /
          get_contract_detail. Panduan mencakup aturan Smart Pagination dan
          flag [INSTRUKSI SISTEM] yang disisipkan tool saat data kontrak
          melebihi threshold tampilan.
  v1.2 — Perbaiki karakter stray di _CONTRACT_TOOL_GUIDANCE baris panduan A).
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# Window & Budget Constants
# ══════════════════════════════════════════════════════════════════════════════

# Jumlah pesan sebelumnya yang disertakan sebagai konteks (2 turns = 4 messages).
# Dikurangi dari 6 → 4 (v8.0). Setiap tambahan pesan memperbesar task description
# yang masuk ke setiap LLM call. Dengan supplier query berisi data tabel panjang
# di riwayat, lebih besar task = lebih tinggi risiko token explosion.
_HISTORY_WINDOW: int = 4

# Batas karakter per pesan asisten di history.
# Mencegah tabel data panjang (supplier, komputer) membengkakkan task description
# di setiap turn berikutnya. User message TIDAK dipotong.
_MAX_ASSISTANT_CONTENT: int = 400

# Batas karakter jawaban yang disimpan ke session history.
# Cukup untuk memberi tahu agent bahwa topik sudah dijawab, tanpa membawa
# seluruh tabel data ke prompt berikutnya.
_MAX_STORED_ANSWER_LEN: int = 500


# ══════════════════════════════════════════════════════════════════════════════
# Guidance Strings (static, disuntikkan ke setiap task description)
# ══════════════════════════════════════════════════════════════════════════════

_LARGE_DATA_GUIDANCE: str = """\
[PANDUAN INTERPRETASI HASIL TOOL — DATA BESAR]

Tools inventaris komputer (get_all_computers, get_computers_by_*) mengembalikan
output dalam format SMART PAGINATION:

  ✅ Total: X.XXX komputer ditemukan di GLPI.
  ⚠️  Data terlalu besar — menampilkan YY sampel pertama.
  📊 Statistik Distribusi: Status / Lokasi / OS
  [baris-baris data sampel]
  📌 ... dan ZZZ item lainnya tidak ditampilkan.

ATURAN WAJIB PENCARIAN ASET / KOMPUTER:
1. "Total: X.XXX" = JUMLAH EXACT dari database — gunakan ini untuk pertanyaan count.
2. Flag ⚠️ = data ditampilkan hanyalah SAMPLE — sampaikan ke user.
3. Untuk menghitung JUMLAH TOTAL KESELURUHAN ASET (Semua jenis aset) → WAJIB gunakan tool `count_all_assets`.
4. Untuk menghitung JUMLAH TOTAL KOMPUTER SAJA → WAJIB gunakan tool `count_all_computers`.
5. ⛔ LARANGAN KERAS: JANGAN panggil `get_all_computers` hanya untuk mendapatkan total aset. 
6. Untuk count by filter → get_computers_by_location / get_computers_by_status.

FORMAT OUTPUT KOMPUTER:
Gunakan TABEL MARKDOWN untuk daftar komputer:
| ID | Nama | Serial | OS | Lokasi | Status |
|---|---|---|---|---|---|
Jangan gunakan bullet list untuk data tabular.

PEMETAAN INTENT ASET & KOMPUTER → TOOL:
"Ada berapa total aset GLPI saat ini"  → count_all_assets()
"Berapa jumlah aset"                   → count_all_assets()
"Berapa jumlah komputer"               → count_all_computers()
"Tampilkan semua komputer"             → get_all_computers()
"Berapa total / jumlah X?"             → WAJIB panggil tool count_X()
"Daftarkan / tampilkan X?"             → Panggil tool get_X()
"""

_SUPPLIER_TOOL_GUIDANCE: str = """\
[PANDUAN PENGGUNAAN TOOL SUPPLIER — WAJIB DIIKUTI]
Tersedia DUA tool supplier — pilih yang tepat:
A) count_suppliers  → HANYA menghitung jumlah total (1 API call, ~1 detik)
   Gunakan untuk: "ada berapa supplier?", "total vendor?", pertanyaan COUNT.
B) get_suppliers    → List/cari supplier dengan detail lengkap
   Parameter filter (semua opsional, dikombinasi AND):
   name / entity / address / phone / fax / email / limit (default 5, MAKS 20)

ATURAN WAJIB UNTUK "DAFTAR SEMUA" / "TAMPILKAN SEMUA SUPPLIER":
1. PANGGIL get_suppliers(limit=5) — SEKALI SAJA.
2. Tool mengembalikan totalcount exact + sampel ≤ 5 baris TERBARU.
3. Setelah tool mengembalikan output dengan [INSTRUKSI SISTEM — WAJIB DIIKUTI]:
   → TULIS Final Answer LANGSUNG. JANGAN panggil tool apapun lagi.
   → JANGAN coba limit lebih besar, offset berbeda, atau filter tambahan
     hanya untuk mendapatkan "sisa" data.
4. Sampaikan ke user: "Terdapat X supplier terdaftar. Berikut 5 data terbaru.
   Sebutkan nama/kota/email spesifik jika ingin mencari supplier tertentu."

⛔ LARANGAN KERAS: Memanggil get_suppliers lebih dari SATU KALI per pertanyaan
   (kecuali filter berbeda karena user meminta supplier spesifik).
   Looping tool untuk pagination = TIMEOUT SISTEM → user tidak mendapat jawaban.

FORMAT OUTPUT SUPPLIER:
Gunakan TABEL MARKDOWN untuk daftar supplier:
| ID | Nama | Entity | Alamat | Telepon |
|---|---|---|---|---|
Jangan gunakan bullet list untuk data tabular.

PEMETAAN INTENT → TOOL:
"ada berapa total supplier?"           → count_suppliers()
"daftar semua supplier"                → get_suppliers(limit=5) — SEKALI SAJA
"berikan detail supplier SYNNEX"       → get_suppliers(name="SYNNEX")
"supplier yang alamatnya di Jakarta"   → get_suppliers(address="Jakarta")
"berapa supplier + daftarnya"          → count_suppliers() LALU get_suppliers(limit=5)
"Berapa total / jumlah X?"             → WAJIB panggil tool count_X()
"Daftarkan / tampilkan X?"             → Panggil tool get_X()
"""

_CONTRACT_TOOL_GUIDANCE: str = """\
[PANDUAN KONTRAK]
- User tanya JUMLAH -> count_contracts()
- User tanya DAFTAR -> list_all_contracts()
- JANGAN panggil keduanya sekaligus. list_all_contracts sudah memberikan total count.
- Jika data > 5, cukup sebutkan totalnya dan berikan 5 sampel saja.

ATURAN WAJIB UNTUK "DAFTAR SEMUA" / "TAMPILKAN SEMUA KONTRAK":
1. PANGGIL list_all_contracts() — SEKALI SAJA.
2. Jika total > 5: tampilkan 5 sampel saja dan sebutkan totalnya ke user.
3. Setelah tool mengembalikan output dengan [INSTRUKSI SISTEM — WAJIB DIIKUTI]:
   → TULIS Final Answer LANGSUNG. JANGAN panggil tool apapun lagi.
   → JANGAN coba limit lebih besar atau filter tambahan untuk mendapatkan "sisa" data.
4. Sampaikan ke user: "Terdapat X kontrak terdaftar. Berikut 5 sampel.
   Sebutkan nama atau ID spesifik jika ingin melihat detail kontrak tertentu."

⛔ LARANGAN KERAS: Memanggil list_all_contracts lebih dari SATU KALI per pertanyaan
   (kecuali filter berbeda karena user meminta kontrak spesifik).
   Looping tool untuk pagination = TIMEOUT SISTEM → user tidak mendapat jawaban.

FORMAT OUTPUT KONTRAK:
Gunakan TABEL MARKDOWN untuk daftar kontrak:
| ID | Nama | Nomor | Tipe | Status |
|---|---|---|---|---|
Jangan gunakan bullet list untuk data tabular.

PEMETAAN INTENT → TOOL:
"ada berapa kontrak?"                     → count_contracts()
"daftar semua kontrak"                    → list_all_contracts() — SEKALI SAJA
"kontrak yang masih aktif"                → list_all_contracts(active_only=True)
"kontrak untuk komputer ID 42"            → list_all_contracts(computer_id=42)
"detail kontrak ID 7"                     → get_contract_detail(contract_id=7)
"info kontrak maintenance server"         → list_all_contracts() → cari ID → get_contract_detail()
"kontrak aktif milik PC-MARKETING-01"     → search_computer("PC-MARKETING-01") → list_all_contracts(computer_id=<id>, active_only=True)
"berapa kontrak + daftarnya"              → list_all_contracts()
"Berapa total / jumlah X?"                → WAJIB panggil tool count_X()
"Daftarkan / tampilkan X?"                → Panggil tool get_X()
"""


# ══════════════════════════════════════════════════════════════════════════════
# Relevance-Based Guidance Selection
# ══════════════════════════════════════════════════════════════════════════════
#
# MENGAPA INI ADA (analisis log produksi 2026-08-31):
#   Sebelumnya KETIGA blok panduan (_LARGE_DATA_GUIDANCE, _SUPPLIER_*,
#   _CONTRACT_*) selalu disuntikkan ke task description. Totalnya ~3.500 token.
#
#   Task description dikirim ULANG pada SETIAP LLM call dalam satu ReAct loop.
#   Untuk 4 call, ~14.000 token terbuang hanya untuk panduan — termasuk panduan
#   komputer/aset saat user hanya bertanya soal kontrak & supplier.
#
#   Dampak terukur di log: LLM call terakhir memakan 51 detik (13:52:16 →
#   13:53:07) sehingga total 84s > server timeout 80s. Memangkas panduan yang
#   tidak relevan adalah cara paling efektif menurunkan latensi, karena waktu
#   inferensi tumbuh seiring panjang prompt.
#
# STRATEGI:
#   Cocokkan keyword pada pertanyaan user. Jika tidak ada yang cocok (pertanyaan
#   ambigu), sertakan SEMUA panduan agar perilaku tidak menjadi lebih buruk
#   daripada sebelumnya — fail-safe, bukan fail-fast.

_COMPUTER_KEYWORDS: tuple[str, ...] = (
    "komputer", "computer", "pc", "laptop", "aset", "asset", "inventaris",
    "inventory", "os", "operating system", "windows", "linux", "lokasi",
    "location", "status", "serial", "hostname",
)

_SUPPLIER_KEYWORDS: tuple[str, ...] = (
    "supplier", "vendor", "pemasok", "penyedia", "distributor",
)

_CONTRACT_KEYWORDS: tuple[str, ...] = (
    "kontrak", "contract", "perjanjian", "sla", "maintenance", "lisensi",
    "license", "berlangganan", "subscription",
)


def _select_guidance(user_message: str) -> str:
    """Pilih blok panduan yang relevan dengan pertanyaan user.

    Memangkas task description secara signifikan (~3.500 → ~1.200 token untuk
    pertanyaan spesifik domain), yang langsung menurunkan latensi setiap LLM
    call dalam ReAct loop.

    Args:
        user_message: Pertanyaan terbaru dari user.

    Returns:
        Gabungan blok panduan yang relevan, dipisah newline. Jika tidak ada
        keyword yang cocok, kembalikan SEMUA panduan (fail-safe untuk
        pertanyaan ambigu seperti "tampilkan semua data").
    """
    msg = user_message.lower()

    blocks: list[str] = []
    if any(k in msg for k in _COMPUTER_KEYWORDS):
        blocks.append(_LARGE_DATA_GUIDANCE)
    if any(k in msg for k in _SUPPLIER_KEYWORDS):
        blocks.append(_SUPPLIER_TOOL_GUIDANCE)
    if any(k in msg for k in _CONTRACT_KEYWORDS):
        blocks.append(_CONTRACT_TOOL_GUIDANCE)

    # Fail-safe: pertanyaan ambigu tetap mendapat konteks penuh.
    if not blocks:
        return "\n".join((
            _LARGE_DATA_GUIDANCE,
            _SUPPLIER_TOOL_GUIDANCE,
            _CONTRACT_TOOL_GUIDANCE,
        ))

    return "\n".join(blocks)


# ══════════════════════════════════════════════════════════════════════════════
# History Formatter
# ══════════════════════════════════════════════════════════════════════════════

def _format_history(messages: list[dict[str, str]], current_message: str) -> str:  # noqa: ARG001
    """Format riwayat percakapan sebelumnya menjadi blok konteks terbaca.

    Mengecualikan pesan user terakhir (pertanyaan saat ini) karena sudah
    ditampilkan di blok [PERTANYAAN TERBARU DARI USER].

    Pesan asisten yang panjang dipotong ke _MAX_ASSISTANT_CONTENT karakter
    untuk mencegah task description membengkak saat ada riwayat dengan
    tabel data besar (supplier list, komputer inventory, dll).

    Args:
        messages       : Array pesan lengkap termasuk turn saat ini.
        current_message: Teks pesan user terbaru. Parameter ini sengaja tidak
                         digunakan (noqa ARG001) — disimpan untuk future use
                         seperti logging atau dedup check.

    Returns:
        String riwayat terformat siap dimasukkan ke task description,
        atau string kosong jika tidak ada riwayat yang relevan.
    """
    if not messages:
        return ""

    # Temukan indeks pesan user terakhir (pertanyaan saat ini)
    last_user_idx: int = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    prior    = messages[:last_user_idx] if last_user_idx > 0 else []
    windowed = prior[-_HISTORY_WINDOW:]

    if not windowed:
        return ""

    lines: list[str] = []
    for msg in windowed:
        role    = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            # Potong jawaban panjang — cukup _MAX_ASSISTANT_CONTENT karakter
            # untuk memberi konteks bahwa topik sudah dijawab.
            if len(content) > _MAX_ASSISTANT_CONTENT:
                content = (
                    content[:_MAX_ASSISTANT_CONTENT]
                    + "… [ringkasan, data lengkap tersedia via tool jika dibutuhkan]"
                )
            lines.append(f"Asisten: {content}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Task Description Builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_task_description(
    user_message: str,
    glpi_user_id: int,
    all_messages: list[dict[str, str]],
) -> str:
    """Bangun task description lengkap untuk satu request CrewAI.

    Struktur output:
      [KONTEKS SESI]          — user_id & jumlah pesan
      [RIWAYAT PERCAKAPAN]    — prior turns (opsional, hanya jika ada)
      [PERTANYAAN TERBARU]    — pertanyaan user saat ini
      [Aturan Data Besar]     — aturan untuk data > 100 record:
      PANDUAN PENGERJAAN      — tool routing guide lengkap
      _LARGE_DATA_GUIDANCE    — panduan interpretasi data besar
      _SUPPLIER_TOOL_GUIDANCE — panduan khusus tool supplier
      _CONTRACT_TOOL_GUIDANCE — panduan khusus tool kontrak

    Args:
        user_message  : Query user terbaru (pertanyaan saat ini).
        glpi_user_id  : GLPI User ID aktif (0 = tidak diketahui).
        all_messages  : Riwayat percakapan lengkap termasuk turn saat ini.

    Returns:
        String task description yang siap diteruskan ke CrewAI Task().
    """
    history_text = _format_history(all_messages, user_message)

    uid_label = (
        f"user_id={glpi_user_id}"
        if glpi_user_id > 0
        else "user_id=UNKNOWN (jangan panggil tool personal tanpa ID yang valid)"
    )

    user_context_block = (
        "[KONTEKS SESI]\n"
        f"• GLPI User ID aktif : "
        f"{glpi_user_id if glpi_user_id > 0 else '(belum diketahui)'}\n"
        f"• Jumlah pesan dalam riwayat: {len(all_messages)}\n\n"
    )

    history_block = (
        f"[RIWAYAT PERCAKAPAN SEBELUMNYA]\n{history_text}\n\n"
        if history_text
        else ""
    )

    return f"""\
{user_context_block}{history_block}\
[PERTANYAAN TERBARU DARI USER]
"{user_message}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATURAN DATA BESAR:
Jika hasil tool berisi "[INSTRUKSI SISTEM]" → TULIS Final Answer LANGSUNG.
DILARANG panggil tool lagi UNTUK DOMAIN YANG SAMA. Sebut totalcount exact + 5 sampel saja.
PENTING: JANGAN tampilkan/copy teks "[INSTRUKSI SISTEM]" ke user.
Looping tool untuk domain yang sama = TIMEOUT = Error.

ATURAN PERTANYAAN MULTI-DOMAIN:
Jika user menanyakan BEBERAPA domain sekaligus (mis. "kontrak DAN supplier"),
panggil SATU tool untuk SETIAP domain — ini BUKAN looping dan DIPERBOLEHKAN.
Setelah semua domain terpenuhi, langsung tulis Final Answer.

ATURAN FORMAT PEMANGGILAN TOOL (WAJIB):
Action Input HARUS berupa SATU objek JSON tunggal, BUKAN array/list.
✅ BENAR : {{"limit": 5}}
❌ SALAH : [{{"limit": 5}}, {{"name": null}}]
Satu Action = satu tool = satu objek JSON. Jangan gabungkan argumen
beberapa tool dalam satu Action Input.

ATURAN KEJUJURAN DATA (WAJIB):
Jika tool mengembalikan "Error" atau gagal, Anda DILARANG mengarang data.
Katakan terus terang bahwa pengambilan data gagal. JANGAN PERNAH menyebut
nama, angka, alamat, atau ID yang tidak ada di output tool.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PANDUAN PENGERJAAN:

1. Periksa riwayat di atas. Jika user MERUJUK data lama ("komputer tadi", "tiket itu") → JANGAN panggil tool lagi. NAMUN, jika user menanyakan ULANG pertanyaan ("Ada berapa total aset") ATAU meminta Anda mengecek ulang ("Coba cek ulang", "Hitung lagi", dsb), ANDA WAJIB memanggil tool (seperti `count_all_computers`) lagi untuk mendapatkan data terbaru dan JANGAN menebak dari memori chat lama!

2. Jika data belum ada di memori chat atau user minta cek ulang, pilih tool yang sesuai:
   • Total/Hitung (Aset/Computer/Supplier) → count_all_assets / count_all_computers / count_suppliers
   • Total/Hitung Kontrak             → count_contracts
   • Daftar Komputer (Semua/Filter)   → get_all_computers / search_computer
   • Komputer by Status/Lokasi/OS     → get_computers_by_status / _location / _os
   • Tiket/Aset/Profil (Milik Saya)   → get_user_tickets / get_user_assets / get_user_info
   • Detail Spesifik (ID)             → get_computer_detail / get_contract_detail
   • Supplier / KB / ITIL             → get_suppliers / search_knowledge_base / get_itil_categories
   • Kontrak (Hitung/Daftar/Detail)   → count_contracts / list_all_contracts / get_contract_detail

3. Gunakan {uid_label} jika tool membutuhkan user_id.

{_select_guidance(user_message)}

4. Final Answer: Bahasa Indonesia, sopan, NO JSON/Thought/Action tags.
   FORMAT OUTPUT (WAJIB):
   • Jika data berbentuk list/daftar → gunakan TABEL MARKDOWN.
   • Kolom: sesuaikan dengan tipe data (ID, Nama, Status, Tanggal, dll).
   • Contoh tabel:
     | ID | Nama Kontrak | Nomor | Tipe |
     |---|---|---|---|
     | 1 | CATIA | 010/AHMIDE-NSI/III-2018 | Software Assurance |
   • Gunakan bullet list hanya untuk penjelasan/ringkasan non-tabular.
   • Code block untuk error message/log/output teknis.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


# ══════════════════════════════════════════════════════════════════════════════
# History Compression
# ══════════════════════════════════════════════════════════════════════════════

def _compress_for_history(answer: str) -> str:
    """Ringkas jawaban panjang sebelum disimpan ke session history.

    Strategi: ambil _MAX_STORED_ANSWER_LEN karakter pertama + tag ringkasan.
    Cukup untuk memberi tahu agent bahwa topik sudah dijawab pada turn
    berikutnya, tanpa membawa seluruh tabel data ke prompt.

    Args:
        answer: Jawaban final dari agent (sudah di-sanitize).

    Returns:
        Jawaban asli jika ≤ _MAX_STORED_ANSWER_LEN, atau versi terpotong
        dengan tag "[jawaban dipotong...]" jika lebih panjang.
    """
    if len(answer) <= _MAX_STORED_ANSWER_LEN:
        return answer
    return (
        answer[:_MAX_STORED_ANSWER_LEN]
        + "\n… [jawaban dipotong untuk efisiensi konteks. "
        + "Panggil tool kembali jika detail lengkap dibutuhkan.]"
    )