**PERTANYAAN ASSESMENT**

1. Mengenai cara kami menarik data dari SCCM, metode apa yang disediakan dan diizinkan oleh pihak AHM? Apakah melalui API bawaan SCCM, koneksi langsung ke Database (DB Link SQL Server), atau ekspor data berkala (misal: CSV)? Kami membutuhkan kepastian ini untuk merancang konektor data (data mapping).

2. Karena sistem ini berada di lingkungan korporat AHM dan belum ada batasan spesifik mengenai tata kelola data (data governance pada 7.2 poin g), apakah AI diizinkan untuk membaca dan memproses data sensitif? (Contoh: data finansial aset, field yang berisi password terenkripsi, atau data personal user).

3. Mekanisme integrasi data dari SCCM ke AI Engine yang paling direkomendasikan oleh tim IT Security AHM seperti apa? Apakah kami akan diberikan akses "Read-Only" ke replika database SQL Server SCCM, menggunakan REST API endpoint SCCM, atau AHM yang akan menyediakan *data dump* terjadwal?

4. Seberapa sering pembaruan data dari SCCM dibutuhkan? Apakah aplikasi harus melakukan *query real-time* saat pengguna meminta *health check*, atau sinkronisasi dilakukan secara *asynchronous* di latar belakang (misalnya sinkronisasi harian menggunakan Cron/Celery)?

5. Apakah saat ini sudah ada *parameter* atau kunci unik (unique key) yang sama antara aset yang tercatat di GLPI dan SCCM (seperti *Serial Number* atau *Asset Tag*)? Hal ini sangat krusial agar logika pemetaan data di aplikasi kami bisa berjalan dengan akurat.

6. Dokumen menyebutkan opsi adanya proses persetujuan (approval) sebelum hasil AI ditampilkan ke pengguna jika diperlukan. Apakah AHM ingin menerapkan alur persetujuan (Human-in-the-loop) ini untuk Fase 2? Jika ya, tipe rekomendasi/tindakan AI seperti apa yang wajib disetujui manajer IT sebelum dieksekusi?

7. Apakah infrastruktur server SCCM dan server GLPI saat ini berada pada jaringan/segmen jaringan yang sama?

8. Apakah implementasi *Celery* dan *Redis* sebagai pekerja latar belakang (*background worker*) diizinkan untuk dijalankan di *environment* Docker yang sama dengan AI Gateway? Mengingat hal ini akan sedikit meningkatkan beban (*resource load*) pada server tersebut.

9. Pada proses *Asset Correlation* (memadankan data SCCM dan GLPI), kami berencana menggunakan urutan pencocokan: *Hostname* -> *Serial Number* -> *MAC Address*. Apakah data *Serial Number* dari SCCM di AHM sering memiliki anomali atau data kosong (misal terisi "To Be Filled By O.E.M.") yang perlu kami antisipasi dengan filter khusus?

10. Kami merancang fitur "Approval Gate" di mana jika ada ketidaksesuaian data antara SCCM dan GLPI (contoh: aset ada di SCCM tapi tidak ada di GLPI), data tersebut akan berstatus *pending_review*. Role atau siapa di AHM yang memiliki wewenang untuk menekan tombol *Approve/Reject* pada sinkronisasi data ini?

11. Terkait pembuatan fitur *Health Score* (Skor Kesehatan Aset), metrik atau parameter operasional apa saja yang digunakan oleh standar IT AHM untuk menentukan sebuah aset itu "sehat" atau "berisiko"? (Kami butuh informasi ini untuk menyesuaikan logika dan bobot penilaian sistem).

12. Berapa rata-rata jumlah endpoint/aset yang saat ini dikelola di SCCM AHM? Mengingat belum pasti apakah penarikan data menggunakan API atau akses langsung ke DB, informasi volume data ini penting bagi kami untuk melakukan *tuning* performa, seperti penerapan *Keyset Pagination* saat korelasi data massal.

13. Terkait keamanan sistem, API Gateway akan menggunakan 2 token berbeda: satu khusus untuk *Chat* dan satu lagi khusus untuk eksekusi korelasi internal. Apakah AHM mensyaratkan standar otentikasi tambahan (misalnya implementasi *IP Whitelisting*) pada *endpoint* internal ini?

14. Untuk fitur Laporan Audit (Audit Trail) yang mencatat log siapa saja yang melakukan *approve/reject* sinkronisasi data, kami menggunakan database SQLite lokal dengan penyimpanan persisten (*volume mount*). Berapa lama durasi AHM mewajibkan data log audit ini disimpan berdasarkan aturan regulasi internal?

15. Dalam skenario terburuk di mana koneksi ke database SCCM terputus atau server SCCM sedang dalam perbaikan (down), apakah AI diizinkan tetap memberikan jawaban hanya dengan data terbatas dari GLPI (tanpa analisis hardware/patch), atau AI harus mengeluarkan peringatan standar bahwa sistem sedang dalam gangguan?