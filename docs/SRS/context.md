# Context: GLPI AI Chatbot Ecosystem

## Glossary

### GLPI AI Chatbot Ecosystem
Sistem asisten virtual cerdas yang terintegrasi langsung di dalam GLPI. Sistem ini terdiri dari dua komponen utama: **GLPI Plugin (Frontend/PHP)** sebagai antarmuka pengguna dan penyimpan data historis, serta **FastAPI Engine (Backend/Python)** sebagai mesin pemroses logika AI dan orkestrasi tools.

### GLPI Plugin (Frontend Component)
Modul native (Plugin) yang diinstal pada server GLPI (`/var/www/glpi/plugins/chatbot`). Plugin ini menambahkan menu "AI Chatbot" pada sidebar, menyediakan antarmuka obrolan interaktif (HTML/JS/CSS), dan menyimpan riwayat percakapan secara persisten di database relasional (MySQL/MariaDB) bawaan GLPI.

### FastAPI Engine (Backend Component)
Layanan microservice berbasis Python (FastAPI) yang memproses permintaan obrolan dari Plugin GLPI. Mesin ini bertugas menghubungi LLM (Language Model), mengeksekusi "Tools" (API request kembali ke GLPI) melalui CrewAI, dan merangkum jawaban.

### Persistent Chat History
Berbeda dengan penyimpanan *in-memory* yang hilang saat *restart*, arsitektur plugin menyimpan metadata sesi (`glpi_plugin_chatbot_sessions`) dan isi pesan (`glpi_plugin_chatbot_messages`) secara permanen di database GLPI. Ini memungkinkan pengguna (user) untuk melihat kembali riwayat percakapannya.

### Intent Routing
Mekanisme di sisi FastAPI Engine yang menggunakan LLM untuk mengklasifikasikan niat (intent) dari pesan pengguna, membedakan antara percakapan *casual* (sapaan) dan *technical* (kueri data ITAM).

### Read-Only Tools
Operasi pengambilan data dari database GLPI (Komputer, Kontrak, Supplier, Tiket, KB) oleh Agen AI yang bersifat hanya baca. AI tidak dapat mengubah, membuat, atau menghapus data di GLPI.
