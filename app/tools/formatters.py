"""app/tools/formatters.py — Presenter / Formatter Layer.

Lapisan ini HANYA bertugas mengubah data mentah (dict / list / PagedResult)
menjadi string teks yang dioptimalkan untuk token LLM.

ATURAN KERAS:
  - Tidak boleh melakukan pemanggilan HTTP, database, atau I/O apapun.
  - Tidak boleh mengimpor modul infrastruktur atau repository.
  - Semua fungsi bersifat pure (input data → output string).

Fungsi yang tersedia:
  Computer:
    _fmt_computer_row()         — satu baris ringkas per komputer
    _fmt_computer_full_detail() — blok detail lengkap satu komputer
    _fmt_paged_header()         — header informatif untuk hasil paginated
    _build_summary_stats()      — statistik distribusi status/lokasi/OS
    _render_paged_result()      — render PagedResult computer → string LLM

  Supplier:
    _fmt_supplier_row()         — blok ringkas satu supplier
    _render_supplier_result()   — render PagedResult supplier → string LLM
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Hanya untuk type hint — tidak di-import saat runtime agar formatter
    # tetap bebas dari ketergantungan ke lapisan repository.
    from app.repository.asset_repository import PagedResult

# ── Threshold konstanta ───────────────────────────────────────────────────────

# Jika jumlah data (totalcount) > SUMMARY_THRESHOLD, tools akan menampilkan
# summary statistik + sample, bukan semua baris detail.
SUMMARY_THRESHOLD: int = 100

# Jumlah baris detail yang ditampilkan ke LLM saat data melebihi SUMMARY_THRESHOLD.
SAMPLE_FOR_LLM: int = 50

# Threshold supplier: jika totalcount > nilai ini, render hanya sampel + header.
# Nilai 5 memastikan bahkan query dengan 6+ supplier langsung masuk jalur sampel.
SUPPLIER_SAMPLE_THRESHOLD: int = 5

# Jumlah baris supplier yang benar-benar dikirim ke LLM saat totalcount > threshold.
# 5 baris × 6 field ≈ 30 baris teks — representatif dan aman untuk token budget.
SUPPLIER_DISPLAY_MAX: int = 5


# ══════════════════════════════════════════════════════════════════════════════
# Computer Formatters
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_computer_row(idx: int, comp: dict[str, Any], detail: bool = False) -> str:
    """Format satu komputer menjadi baris teks ringkas dan hemat token.

    Mode ringkas (detail=False):
      Satu baris inline per komputer. Menghemat ~40% token dibanding block
      multi-baris versi lama.

    Mode detail (detail=True):
      Multi-baris dengan semua field yang tersedia. Digunakan untuk tampilan
      yang lebih lengkap pada dataset kecil.

    Args:
        idx   : Nomor urut (1-based).
        comp  : Dict data komputer mentah dari repository.
        detail: True untuk format multi-baris, False untuk format satu baris.

    Returns:
        String terformat, diakhiri newline.
    """
    name   = comp.get("name") or "-"
    cid    = comp.get("id") or "-"
    serial = comp.get("serial") or "-"
    status = comp.get("status") or "-"
    loc    = comp.get("location") or "-"
    os_    = comp.get("os") or "-"

    if not detail:
        # Mode ringkas: satu baris per komputer
        return (
            f"{idx}. {name} (ID:{cid}) | SN:{serial} | "
            f"Status:{status} | Lokasi:{loc} | OS:{os_}\n"
        )

    # Mode detail: multi-baris dengan semua field
    lines = [f"{idx}. **{name}** (ID: {cid})"]

    def _add(label: str, key: str) -> None:
        val = comp.get(key) or "(tidak ada)"
        lines.append(f"   {label:<18}: {val}")

    _add("Serial Number",   "serial")
    _add("Inventory Number","otherserial")
    _add("Type",            "type")
    _add("Model",           "model")
    _add("Status",          "status")
    _add("Lokasi",          "location")
    _add("User",            "user")
    if comp.get("entity"):
        _add("Entity",      "entity")
    if comp.get("manufacturer"):
        _add("Pabrikan",    "manufacturer")
    if comp.get("os"):
        _add("OS",          "os")
    if comp.get("date_mod"):
        _add("Terakhir Update", "date_mod")

    lines.append("   --- Data Finansial ---")
    _add("  Tgl Beli",      "buy_date")
    _add("  Tgl Pakai",     "use_date")
    warranty = comp.get("warranty_duration") or "(tidak ada)"
    lines.append(f"   {'Garansi':<18}: {warranty} bulan")
    if comp.get("warranty_date"):
        _add("  Garansi Berakhir", "warranty_date")
    _add("  Nilai Aset",    "value")
    _add("  Supplier",      "supplier")

    contracts: list[dict[str, Any]] = comp.get("contracts") or []
    if contracts:
        lines.append("   Kontrak terkait:")
        for c in contracts:
            end = c.get("end_date") or "(tidak ada)"
            lines.append(
                f"     - {c.get('name', '-')} (ID: {c.get('id', '-')}) | Berakhir: {end}"
            )

    return "\n".join(lines) + "\n"


def _fmt_computer_full_detail(comp: dict[str, Any]) -> str:
    """Format detail lengkap SATU komputer untuk GetComputerDetailTool.

    Menampilkan semua 16 field standar dalam format key-value kolom yang
    konsisten dan mudah dibaca oleh LLM maupun user. Setiap field selalu
    ditampilkan (dengan nilai "(tidak ada)" jika kosong) sehingga tidak ada
    informasi yang tersembunyi karena kondisional.

    Field yang ditampilkan:
      1.  Name                              9.  Alternate Username Number (contact_num)
      2.  Entity                            10. Alternate Username (contact)
      3.  Serial Number                     11. Operating System - Name
      4.  Inventory Number (otherserial)    12. Status
      5.  Location                          13. Financial - Startup Date (use_date)
      6.  Type                              14. Comments
      7.  Model                             15. Documents - Number of Documents
      8.  Manufacturer                      16. Last Update

    Field tambahan jika tersedia:
      - OS Version & Architecture
      - Supplier (dari infocom)
      - Kontrak terkait (nama, nomor, tanggal berakhir)

    Args:
        comp: Dict data komputer mentah dari repository.

    Returns:
        String terformat lengkap, diakhiri newline.
    """
    def _v(key: str) -> str:
        """Ambil nilai field, kembalikan '(tidak ada)' jika kosong."""
        val = comp.get(key)
        if val is None or str(val).strip() in ("", "0", "None"):
            return "(tidak ada)"
        return str(val).strip()

    cid  = comp.get("id") or "-"
    name = comp.get("name") or "-"
    W    = 28  # lebar kolom label

    def _row(label: str, value: str) -> str:
        return f"  {label:<{W}}: {value}"

    lines = [
        "══════════════════════════════════════════════",
        f"  Detail Komputer: {name}  (ID: {cid})",
        "══════════════════════════════════════════════",
        "",
        "── Identitas ──────────────────────────────────",
        _row("Name",                      name),
        _row("Entity",                    _v("entity")),
        _row("Serial Number",             _v("serial")),
        _row("Inventory Number",          _v("otherserial")),
        _row("Location",                  _v("location")),
        _row("Type",                      _v("type")),
        _row("Model",                     _v("model")),
        _row("Manufacturer",              _v("manufacturer")),
        _row("Alternate Username Number", _v("contact_num")),
        _row("Alternate Username",        _v("contact")),
        "",
        "── Sistem Operasi ─────────────────────────────",
        _row("Operating System - Name",   _v("os")),
    ]

    # Tampilkan versi & arsitektur hanya jika tersedia dan berbeda dari nama OS
    if comp.get("os_version") and comp.get("os_version") not in (comp.get("os"), ""):
        lines.append(_row("  OS Version",      _v("os_version")))
    if comp.get("os_arch"):
        lines.append(_row("  OS Architecture", _v("os_arch")))

    lines += [
        "",
        "── Status & Pengguna ──────────────────────────",
        _row("Status",                    _v("status")),
        _row("User",                      _v("user")),
        "",
        "── Informasi Finansial & Administratif ────────",
        _row("Startup Date (use_date)",   _v("use_date")),
        _row("Buy Date",                  _v("buy_date")),
        _row(
            "Warranty Duration",
            f"{_v('warranty_duration')} bulan"
            if comp.get("warranty_duration") else "(tidak ada)",
        ),
        _row("Warranty Expiry",           _v("warranty_date")),
        _row("Asset Value",               _v("value")),
        _row("Supplier (Financial)",      _v("supplier")),
        "",
        "── Dokumen & Catatan ──────────────────────────",
    ]

    doc_count = comp.get("doc_count", 0)
    lines.append(_row("Documents - Number", str(doc_count) if doc_count else "0"))

    comment = (comp.get("comment") or "").strip()
    if comment:
        comment_display = comment[:400] + ("..." if len(comment) > 400 else "")
        lines.append(_row("Comments", comment_display))
    else:
        lines.append(_row("Comments", "(tidak ada)"))

    lines += [
        "",
        "── Metadata ───────────────────────────────────",
        _row("Last Update", _v("date_mod")),
    ]

    # Kontrak terkait
    contracts: list[dict[str, Any]] = comp.get("contracts") or []
    if contracts:
        lines.append("")
        lines.append("── Kontrak Terkait ─────────────────────────────")
        for c in contracts:
            c_name = c.get("name") or "-"
            c_num  = c.get("num") or "(no num)"
            c_end  = c.get("end_date") or "(tidak ada)"
            c_id   = c.get("id") or "-"
            lines.append(f"  • {c_name} (ID: {c_id}) | No: {c_num} | Berakhir: {c_end}")
    else:
        lines.append("")
        lines.append(_row("Kontrak Terkait", "(tidak ada)"))

    lines.append("══════════════════════════════════════════════")
    return "\n".join(lines) + "\n"


def _fmt_paged_header(
    totalcount: int,
    fetched: int,
    truncated: bool,
    context: str = "komputer",
    filter_label: str = "",
) -> str:
    """Buat header informatif untuk output data paginated.

    Tiga skenario yang ditangani:
      1. Data kecil (≤ SUMMARY_THRESHOLD, tidak truncated) → header singkat tanpa warning.
      2. Data besar tapi truncated → tampilkan total + peringatan sample.
      3. Data besar tapi semua berhasil di-fetch → tampilkan total + jumlah item.

    Args:
        totalcount  : Jumlah exact dari API GLPI.
        fetched     : Jumlah item yang benar-benar di-fetch ke memori.
        truncated   : True jika ada data yang tidak di-fetch (totalcount > fetched).
        context     : Label jenis data (mis: "komputer", "komputer aktif").
        filter_label: Label filter tambahan (mis: "di lokasi 'Lantai 3'").

    Returns:
        String header yang siap digabungkan dengan body output.

    Example output (kasus truncated):
        ✅ Total: **23.450 komputer** ditemukan di GLPI.
        ⚠️  Data terlalu besar — menampilkan 50 sampel pertama. ...
    """
    filter_part = f" {filter_label}" if filter_label else ""
    total_fmt   = f"{totalcount:,}".replace(",", ".")

    if not truncated and totalcount <= SUMMARY_THRESHOLD:
        return f"✅ Ditemukan {total_fmt} {context}{filter_part}.\n\n"

    if truncated:
        sample_fmt = f"{fetched:,}".replace(",", ".")
        return (
            f"✅ Total: **{total_fmt} {context}** ditemukan{filter_part} di GLPI.\n"
            f"⚠️  Data terlalu besar — menampilkan {sample_fmt} sampel pertama. "
            f"Gunakan filter (status/lokasi/OS/nama) untuk mempersempit hasil.\n\n"
        )

    # Semua data berhasil di-fetch tapi jumlahnya besar
    fetched_fmt = f"{fetched:,}".replace(",", ".")
    return (
        f"✅ Total: **{total_fmt} {context}** ditemukan{filter_part}. "
        f"Menampilkan {fetched_fmt} item:\n\n"
    )


def _build_summary_stats(
    items: list[dict[str, Any]],
    totalcount: int,
    truncated: bool,
) -> str:
    """Buat statistik ringkasan distribusi status, lokasi, dan OS.

    Jika data ter-truncate, statistik hanya berdasarkan sample yang ada
    (dengan keterangan). Jika semua data ada, statistik akurat 100%.

    Args:
        items     : List computer dicts yang sudah di-fetch.
        totalcount: Jumlah total dari API.
        truncated : True jika items adalah subset dari totalcount.

    Returns:
        String statistik terformat, atau "" jika items kosong.
    """
    if not items:
        return ""

    scope_note = (
        f" (berdasarkan {len(items):,} sampel dari {totalcount:,} total)".replace(",", ".")
        if truncated else ""
    )

    status_counts   = Counter(c.get("status")   or "Tidak diketahui" for c in items)
    location_counts = Counter(c.get("location") or "Tidak diketahui" for c in items)
    os_counts       = Counter(c.get("os")       or "Tidak diketahui" for c in items)

    def _fmt_counter(counter: Counter, top_n: int = 5) -> str:
        lines = []
        for val, cnt in counter.most_common(top_n):
            pct = cnt * 100 / len(items)
            lines.append(f"   • {val}: {cnt:,} ({pct:.0f}%)".replace(",", "."))
        if len(counter) > top_n:
            lines.append(f"   • ... dan {len(counter) - top_n} kategori lainnya")
        return "\n".join(lines)

    return (
        f"📊 **Statistik Distribusi**{scope_note}:\n"
        f"  Status:\n{_fmt_counter(status_counts)}\n"
        f"  Lokasi (top 5):\n{_fmt_counter(location_counts)}\n"
        f"  Sistem Operasi:\n{_fmt_counter(os_counts)}\n\n"
    )


def _render_paged_result(
    result: "PagedResult",
    context: str = "komputer",
    filter_label: str = "",
    show_stats: bool = True,
) -> str:
    """Render PagedResult menjadi string output yang LLM-friendly.

    Logika render:
      - Data kecil (totalcount ≤ SUMMARY_THRESHOLD): tampilkan semua baris detail.
      - Data besar (totalcount > SUMMARY_THRESHOLD): header + statistik +
        SAMPLE_FOR_LLM baris pertama sebagai representasi.

    Args:
        result      : PagedResult dari repository functions.
        context     : Label jenis data.
        filter_label: Label filter untuk header.
        show_stats  : Jika True, tampilkan summary statistik untuk data besar.

    Returns:
        String lengkap yang siap dikirim ke LLM sebagai tool output.
    """
    items      = result["items"]
    totalcount = result["totalcount"]
    fetched    = result["fetched"]
    truncated  = result["truncated"]

    if not items and totalcount == 0:
        return f"Tidak ada {context} ditemukan."

    header = _fmt_paged_header(totalcount, fetched, truncated, context, filter_label)

    is_large      = totalcount > SUMMARY_THRESHOLD
    display_items = items[:SAMPLE_FOR_LLM] if is_large else items

    stats_section = ""
    if is_large and show_stats:
        stats_section = _build_summary_stats(items, totalcount, truncated)

    rows = "".join(
        _fmt_computer_row(idx, comp)
        for idx, comp in enumerate(display_items, 1)
    )

    footer = ""
    if is_large and len(display_items) < fetched:
        remaining = fetched - len(display_items)
        footer = (
            f"\n📌 ... dan {remaining:,} item lainnya tidak ditampilkan. "
            f"Gunakan filter lebih spesifik untuk mempersempit pencarian.\n"
            .replace(",", ".")
        )
    elif is_large and truncated:
        footer = (
            f"\n📌 Catatan: Sistem memiliki {totalcount:,} {context} total. "
            f"Hanya {SAMPLE_FOR_LLM} sampel ditampilkan. "
            f"Gunakan filter untuk pencarian lebih spesifik.\n"
            .replace(",", ".")
        )

    return header + stats_section + rows + footer


# ══════════════════════════════════════════════════════════════════════════════
# Supplier Formatters
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_supplier_row(idx: int, supplier: dict[str, Any]) -> str:
    """Format satu supplier menjadi blok teks ringkas dan informatif.

    Menampilkan keenam kolom utama dasbor GLPI:
      Name, Entity, Address (gabungan), Phone, Fax, Email.

    Args:
        idx     : Nomor urut (1-based).
        supplier: Dict data supplier mentah dari repository.

    Returns:
        String multi-baris terformat (tanpa trailing newline tambahan).
    """
    def _val(key: str) -> str:
        return str(supplier.get(key) or "").strip() or "(tidak ada)"

    name   = supplier.get("name") or "-"
    sid    = supplier.get("id")
    id_str = str(sid) if sid and str(sid) not in ("", "0") else "-"

    return (
        f"{idx}. {name} (ID: {id_str})\n"
        f"   Entity  : {_val('entity')}\n"
        f"   Alamat  : {_val('address')}\n"
        f"   Telepon : {_val('phone')}\n"
        f"   Fax     : {_val('fax')}\n"
        f"   Email   : {_val('email')}\n"
    )


def _render_supplier_result(
    result: "PagedResult",
    filter_label: str = "",
) -> str:
    """Render PagedResult supplier menjadi string LLM-friendly.

    Logika render:
      - Data kecil (totalcount ≤ SUPPLIER_SAMPLE_THRESHOLD): tampilkan semua.
      - Data besar: tampilkan header total + SUPPLIER_DISPLAY_MAX baris sampel
        + instruksi sistem untuk mencegah agent looping.

    Instruksi sistem [INSTRUKSI SISTEM — WAJIB DIIKUTI] disuntikkan di akhir
    output saat data besar untuk mencegah agent memanggil tool lagi dan
    memicu token explosion.

    Args:
        result      : PagedResult dari supplier_repository.
        filter_label: Label filter aktif (mis: "dengan filter nama='Lenovo'").

    Returns:
        String lengkap yang siap dikirim ke LLM sebagai tool output.
    """
    items      = result["items"]
    totalcount = result["totalcount"]
    truncated  = result["truncated"]

    if not items and totalcount == 0:
        filter_note = f" {filter_label}" if filter_label else ""
        return f"Tidak ada supplier ditemukan{filter_note}."

    total_fmt  = f"{totalcount:,}".replace(",", ".")
    filter_str = f" {filter_label}" if filter_label else ""

    is_large      = totalcount > SUPPLIER_SAMPLE_THRESHOLD
    display_items = items[:SUPPLIER_DISPLAY_MAX] if is_large else items

    if not truncated and not is_large:
        # Semua data kecil (≤ SUPPLIER_SAMPLE_THRESHOLD) — tampilkan tanpa warning
        header = f"✅ Ditemukan {total_fmt} supplier{filter_str}.\n\n"
    else:
        sample_fmt = f"{len(display_items):,}".replace(",", ".")
        header = (
            f"✅ Total: **{total_fmt} supplier** ditemukan{filter_str}.\n"
            f"⚠️  Menampilkan {sample_fmt} sampel pertama dari {total_fmt}. "
            f"Gunakan filter (name/entity/address/phone/email) untuk mempersempit hasil.\n\n"
        )

    rows = "".join(
        _fmt_supplier_row(idx, s) + "\n"
        for idx, s in enumerate(display_items, 1)
    )

    footer = ""
    if is_large or truncated:
        remaining     = totalcount - len(display_items)
        remaining_fmt = f"{remaining:,}".replace(",", ".")
        footer = (
            f"\n📌 ... dan {remaining_fmt} supplier lainnya tidak ditampilkan. "
            f"Gunakan filter (name/entity/address/phone/fax/email) "
            f"atau cari dengan nama spesifik untuk hasil lebih sempit.\n"
        )

    # Suntik instruksi sistem untuk menghentikan agent loop saat data besar.
    # Format [INSTRUKSI SISTEM] sengaja mencolok agar diproses agent sebagai
    # perintah eksplisit, bukan sekadar komentar informatif.
    stop_instruction = ""
    if is_large or truncated:
        stop_instruction = (
            f"\n\n[INSTRUKSI SISTEM — WAJIB DIIKUTI]:\n"
            f"Data supplier sudah diterima. Sistem membatasi tampilan untuk "
            f"menjaga performa — INI BUKAN ERROR.\n"
            f"TINDAKAN YANG HARUS DILAKUKAN SEKARANG:\n"
            f"1. TULIS Final Answer langsung — JANGAN panggil tool apapun lagi.\n"
            f"2. Gunakan angka exact dari header: {total_fmt} supplier terdaftar.\n"
            f"3. Tampilkan {len(display_items)} supplier di atas sebagai contoh.\n"
            f"4. Arahkan user untuk filter jika butuh supplier spesifik.\n"
            f"MEMANGGIL TOOL LAGI SETELAH INSTRUKSI INI = PELANGGARAN ATURAN.\n"
            f"TULIS Final Answer SEKARANG!"
        )

    return header + rows + footer + stop_instruction