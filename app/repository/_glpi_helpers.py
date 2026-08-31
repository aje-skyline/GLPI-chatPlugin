"""Shared parsing helpers — GLPI AI Gateway repository layer.

Kumpulan fungsi utilitas kecil yang dipakai oleh lebih dari satu modul
repository. Disatukan di sini untuk menghindari duplikasi dan agar mudah
diuji secara unit.

Semua fungsi di file ini bersifat pure (tidak ada side effect, tidak ada I/O)
sehingga mudah di-mock dan di-test tanpa dependensi eksternal.
"""

import re
from typing import Any


def strip_html(text: str) -> str:
    """Hapus semua tag HTML dari teks GLPI dan normalisasi whitespace.

    GLPI menyimpan field ``comment``, ``answer`` (KB), dan ``content`` (tiket)
    dalam format HTML. LLM tidak membutuhkan tag HTML — teks bersih lebih
    efisien dari segi token.

    Args:
        text: String mentah yang mungkin mengandung tag HTML.

    Returns:
        Teks bersih tanpa tag HTML dan tanpa whitespace berlebih.
        String kosong jika input falsy.
    """
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def clean_value(value: Any) -> str:
    """Normalisasi nilai dropdown GLPI ke string bersih.

    GLPI menyimpan relasi (FK) sebagai integer ID. Dengan ``expand_dropdowns=true``,
    nilai tersebut diganti teks, tapi kadang masih mengembalikan "0" (unset FK).
    Fungsi ini memastikan "0" dikembalikan sebagai string kosong agar UI
    menampilkan "-" bukan "0" yang tidak bermakna.

    Args:
        value: Nilai dari field GLPI (bisa int, str, None, dsb.).

    Returns:
        String bersih, atau ``""`` jika nilai tidak bermakna (None, "0", "None").
    """
    if value is None:
        return ""
    # GLPI versi baru (high-level REST) mengembalikan dropdown sebagai objek
    # nested {"id": 3, "name": "Maintenance"} alih-alih string hasil
    # expand_dropdowns. Tanpa penanganan ini, str(dict) menghasilkan
    # "{'id': 3, 'name': 'Maintenance'}" yang bocor ke jawaban LLM.
    if isinstance(value, dict):
        value = value.get("name") or value.get("completename") or ""
    s = str(value).strip()
    if s in ("", "0", "None"):
        return ""
    return s


def first_of(item: dict[str, Any], *keys: str) -> Any:
    """Kembalikan nilai pertama yang tidak kosong dari item berdasarkan urutan key.

    Digunakan untuk mengambil field dari response GLPI Search API yang
    menggunakan key numerik (``"1"``, ``"2"``, dll.) sebagai field ID,
    sebelum fallback ke nama field konvensional.

    Args:
        item: Satu item dari GLPI Search API response.
        *keys: Key yang dicoba secara berurutan.

    Returns:
        Nilai pertama yang tidak ``None`` dan tidak ``""``, atau ``""`` jika
        semua key menghasilkan nilai kosong.

    Example:
        >>> first_of(item, "2", "id")   # coba key "2" dulu, fallback ke "id"
        "42"
    """
    for k in keys:
        v = item.get(k)
        if v is not None and v != "":
            return v
    return ""


_STATUS_MAP: dict[int, str] = {
    1: "Baru",
    2: "Dalam Proses (Assigned)",
    3: "Dalam Proses (Planned)",
    4: "Menunggu",
    5: "Selesai",
    6: "Ditutup",
}


def ticket_status_label(status: Any) -> str:
    """Konversi status tiket numerik GLPI ke label Bahasa Indonesia.

    Args:
        status: Nilai status dari GLPI (int atau string angka).

    Returns:
        Label status dalam Bahasa Indonesia, atau ``"Status {value}"`` jika
        tidak dikenali, atau ``"Tidak diketahui"`` jika nilai tidak bisa
        di-parse.
    """
    try:
        return _STATUS_MAP.get(int(status), f"Status {status}")
    except (TypeError, ValueError):
        return "Tidak diketahui"