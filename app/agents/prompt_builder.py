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

ATURAN WAJIB:
1. "Total: X.XXX" = JUMLAH EXACT dari database — gunakan ini untuk pertanyaan count.
2. Flag ⚠️ = data ditampilkan hanyalah SAMPLE — sampaikan ke user.
3. Untuk count by filter → get_computers_by_location / get_computers_by_status.
4. JANGAN panggil get_all_computers hanya untuk count → gunakan count_all_computers.
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

PEMETAAN INTENT → TOOL:
"ada berapa total supplier?"           → count_suppliers()
"daftar semua supplier"                → get_suppliers(limit=5) — SEKALI SAJA
"berikan detail supplier SYNNEX"       → get_suppliers(name="SYNNEX")
"supplier yang alamatnya di Jakarta"   → get_suppliers(address="Jakarta")
"berapa supplier + daftarnya"          → count_suppliers() LALU get_suppliers(limit=5)
"""


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
            # untuk memberi konteks bahwa topik ini sudah dijawab.
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
      [Panduan Thought]       — aturan singkat untuk format Thought:
      PANDUAN PENGERJAAN      — tool routing guide lengkap
      _LARGE_DATA_GUIDANCE    — panduan interpretasi data besar
      _SUPPLIER_TOOL_GUIDANCE — panduan khusus tool supplier

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
[Panduan Format Pemikiran (Thought Process)]

Setiap kali kamu menulis "Thought:", WAJIB SINGKAT — maksimal 2-3 kalimat.
Format yang benar:
  Thought: User ingin [X]. Saya akan memanggil tool [Y] untuk mendapatkan data.
  (lalu langsung tulis Action)

Hindari format berikut untuk mencegah error:
  Thought: Baiklah, saya perlu mempertimbangkan bahwa... [paragraf panjang]
  Thought: Menganalisis permintaan user secara mendalam... [repetisi panduan]

Setelah menerima hasil tool → LANGSUNG tulis "Final Answer:" tanpa Thought tambahan.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PANDUAN PENGERJAAN:

1. Periksa riwayat di atas. Jika data sudah ada dan user merujuknya
   ("komputer tadi", "tiket itu") → JANGAN panggil tool lagi.

2. Jika data belum ada, pilih tool yang sesuai:
   • Jumlah/total komputer      → count_all_computers
   • Jumlah/total supplier      → count_suppliers
   • Panduan/KB                 → search_knowledge_base
   • Semua komputer + statistik → get_all_computers
   • Cari komputer              → search_computer
   • Komputer by lokasi         → get_computers_by_location
   • Komputer by status         → get_computers_by_status
   • Komputer by OS             → get_computers_by_os
   • Aset milik user            → get_user_assets ({uid_label})
   • Detail komputer by ID      → get_computer_detail
   • Tiket user                 → get_user_tickets ({uid_label})
   • Profil user                → get_user_info ({uid_label})
   • Kontrak                    → list_all_contracts
   • Detail kontrak by ID       → get_contract_detail
   • Supplier list/detail/cari  → get_suppliers  (lihat panduan bawah)
   • Kategori ITIL              → get_itil_categories

3. WAJIB: Semua tool yang butuh user_id → gunakan {uid_label}.

{_LARGE_DATA_GUIDANCE}

{_SUPPLIER_TOOL_GUIDANCE}

4. Tulis Final Answer dalam Bahasa Indonesia yang sopan dan natural.
   Pastikan output terakhir hanya menggunakan teks natural, bukan JSON,
   "Action:", "Thought:", atau format internal apapun.
   Gunakan angka dari output tool — JANGAN tebak-tebak.
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