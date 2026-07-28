# MIGRASI DAN EKSTENSI AI UNTUK SISTEM GLPI
### PT Astra Honda Motor

> **PERNYATAAN KERAHASIAAN**
> Dokumen ini digolongkan sebagai dokumen rahasia bisnis dan tidak diizinkan untuk diperbanyak sebagian ataupun seluruh isinya atau diberikan kepada siapapun tanpa izin tertulis dari PT Semesta Teknologi Informatika.
>
> Semua hal yang berhubungan dengan sifat dan gambaran, prosedur dan rancangan proposal PT Astra Honda Motor, semua hal yang berhubungan dengan metodologi implementasi, teknik perencanaan dan pengaturan proyek, pengujian dan perancangan sistem digolongkan sebagai informasi yang bersifat rahasia dan tidak boleh diteruskan atau dibuka kepada pihak manapun tanpa izin tertulis dari PT Semesta Teknologi Informatika.
>
> Segala informasi yang ada di dalam dokumen ini digunakan di bawah izin hak cipta dan hanya digunakan atau diperbanyak menurut aturan yang mengikat. Keterangan yang tercantum dalam dokumen ini diberikan hanya untuk kepentingan informasi, dan segala perubahan mungkin saja terjadi, bentuk perubahan merupakan komitmen dari PT Semesta Teknologi Informatika.
>
> Hak Cipta © PT SEMESTA TEKNOLOGI INFORMATIKA. (2026)

---

## Table of Contents

1. [Tentang Kami](#1-tentang-kami)
   - 1.1 [Profil Perusahaan](#11-profil-perusahaan)
   - 1.2 [Customer](#12-customer)
   - 1.3 [Partner](#13-partner)
2. [Pendahuluan](#2-pendahuluan)
3. [Latar Belakang](#3-latar-belakang)
4. [Tujuan dan Manfaat](#4-tujuan-dan-manfaat)
   - 4.1 [Mitigasi Resiko Keamanan Infrastruktur](#41-mitigasi-resiko-keamanan-infrastruktur)
   - 4.2 [Efisiensi Operasional](#42-efisiensi-operasional)
   - 4.3 [Kualitas Pengambil Keputusan](#43-kualitas-pengambil-keputusan)
   - 4.4 [User Experience](#44-user-experience)
   - 4.5 [Nilai Strategis](#45-nilai-strategis)
5. [Rekomendasi Solusi](#5-rekomendasi-solusi)
   - 5.1 [Migrasi Sistem GLPI (Fase Pertama)](#51-migrasi-sistem-glpi-fase-pertama)
   - 5.2 [Ekstensi AI (Fase Kedua)](#52-ekstensi-ai-fase-kedua)
6. [Scope Of Work (SOW)](#6-scope-of-work-sow)
7. [Out of Scope (OOS)](#7-out-of-scope-oos)
8. [Kesimpulan](#8-kesimpulan)

---

## 1. Tentang Kami

### 1.1 Profil Perusahaan

PT Semesta Teknologi Informatika didirikan pada tahun 2012. Kami merupakan perusahaan yang bergerak di bidang IT dengan cakupan bidang Hardware, Software, Networking, Development yang sudah berpengalaman dalam bidangnya. Tidak hanya menyediakan product tapi kami juga menyediakan solusi sesuai dengan kebutuhan customer.

Kami memiliki engineer yang sudah berpengalaman dalam menerapkan solusi infrastruktur seperti Server & Storage, Mail System, Video Conference, Document Management System & Collaboration, Database System dan System Management, Fiber Optic, Core Networking, Routing dan Perimeter Gateway serta sudah berpengalaman dalam bidang IT Security dan juga Compliance.

**Visi:** Menjadi mitra yang tak tergantikan di bidang Teknologi Informasi.

**Misi:** Memberikan teknologi dan pengetahuan terbaik yang memenuhi kebutuhan nyata customer, membawa transformasi dan perubahan dengan mengedukasi sumber daya manusia customer.

Prinsip kerja yang dikedepankan oleh tim Semesta Teknologi Informatika adalah **Integritas, Kerja Tim, Solusi Inovatif, serta Pelayanan Prima** untuk memberikan service terbaik bagi customer.

Kami memiliki layanan after sales yang didukung oleh tim yang profesional dan berpengalaman untuk memastikan kepuasan pelanggan setelah pembelian. Dengan adanya layanan ini, customer dapat menghubungi kami setiap saat untuk mendapatkan bantuan, informasi, atau solusi terkait produk yang telah mereka beli, sehingga memberikan rasa aman dan nyaman dalam menggunakan produk maupun layanan kami. Kami berkomitmen untuk memberikan dukungan yang efektif dan memastikan bahwa setiap masalah dapat diselesaikan dengan segera dan pelanggan selalu merasa dihargai.

### 1.2 Customer

Customer yang telah bersama dan mempercayai kami.

![Daftar Customer](images/customer-logos.jpeg)

### 1.3 Partner

Kami menjalin hubungan yang baik dengan ekosistem vendor penyedia solusi IT terdepan terkait partnership yang merupakan bukti konsistensi kami terhadap pemenuhan kebutuhan customer.

![Daftar Partner](images/partner-logos.jpeg)

---

## 2. Pendahuluan

Dokumen ini merekomendasikan pembaruan versi sistem GLPI serta penambahan kapabilitas AI ke dalam sistem GLPI melalui penggunaan plugins yang didukung oleh AI orchestration engine terpisah, bukan dengan melakukan modifikasi pada core GLPI untuk PT Astra Honda Motor.

Dengan hal ini, beberapa manfaat yang dapat diperoleh antara lain:

a) Menjaga upgradeability dan stabilitas dari platform GLPI.
b) Memungkinkan kapabilitas AI untuk diimplementasikan.
c) Memisahkan user experience, governance, dan runtime AI sehingga tiap komponen dapat dikembangkan secara mandiri dengan resiko minimal.

Rekomendasi awal difokuskan pada pembaruan versi sistem GLPI serta melakukan ekstensifikasi dua kapabilitas AI pada platform GLPI, diantaranya:

a) Asisten berbasis LLM yang dapat memfasilitasi pengguna dan tim IT untuk berinteraksi dengan data GLPI secara lebih efisien.
b) Fungsi analitik pintar yang dapat melakukan tinjauan terhadap data aset, serta mengkorelasikannya dengan informasi dari System Center Configuration Manager (SCCM), mengidentifikasi tren, dan menghasilkan rekomendasi juga risk insights.

Kombinasi kedua kapabilitas ini ditujukan untuk meningkatkan efisiensi layanan, memperkuat pengelolaan siklus aset, serta mendorong penerapan model operasi TI yang lebih cerdas dan prediktif.

> Perlu dicatat bahwa fitur-fitur tersebut merupakan bagian dari solusi GLPI AI secara keseluruhan, bukan terpisah.

Dengan pendekatan ini, GLPI tetap berperan sebagai aplikasi utama yang dikelola dan dikontrol sesuai dengan tata kelola sistem yang berlaku. Sementara itu, AI Engine berfungsi untuk mengorkestrasi agen serta menangani proses yang memerlukan waktu lebih lama atau alur otomatisasi yang lebih kompleks.

## 3. Latar Belakang

Implementasi AI dirancang untuk memberikan nilai tambah terhadap pemanfaatan data operasional melalui:

a) Mempermudah akses informasi di dalam GLPI sehingga pengguna dapat menemukan data atau konteks yang dibutuhkan dengan lebih cepat.
b) Membantu menghubungkan berbagai sumber data operasional agar dapat dilihat sebagai satu gambaran yang utuh.
c) Mendukung proses analisis dengan memberikan ringkasan, konteks, dan rekomendasi awal bagi tim operasional.
d) Mengurangi beban pekerjaan administratif dan pencarian informasi yang manual.
e) Memberikan dukungan insight bagi manajemen untuk memahami kondisi operasional yang terjadi.

---

## 4. Tujuan dan Manfaat

### 4.1 Mitigasi Resiko Keamanan Infrastruktur

Migrasi sistem GLPI dari versi 9.4.4 ke versi 11 dilakukan untuk memitigasi risiko keamanan pada infrastruktur.

### 4.2 Efisiensi Operasional

a) Akselerasi dalam akses dan pencarian informasi operasional di dalam sistem GLPI.
b) Ringkasan otomatis untuk memudahkan penyimpulan.
c) Pengurangan beban kerja (effort) pada tugas-tugas service desk yang rutin dan repetitif.
d) Peningkatan ketepatan prioritas tindakan operasional, terutama terkait pengelolaan aset dan penanganan insiden.

### 4.3 Kualitas Pengambil Keputusan

a) Tersedianya rekomendasi berbasis konteks (context-rich recommendations) yang membantu memperjelas langkah operasional atau teknis yang perlu diambil.
b) Peningkatan visibilitas terhadap pola operasional dan tren kesehatan aset, sehingga analisis diagnostik menjadi lebih cepat dan akurat.
c) Penguatan dasar pengambilan keputusan terkait anggaran, siklus hidup perangkat, dan perencanaan kapasitas melalui insight yang berbasis data.
d) Deteksi lebih dini terhadap indikasi risiko, sehingga mitigasi dapat dilakukan secara proaktif.

### 4.4 User Experience

a) Penyederhanaan interaksi pengguna dengan GLPI melalui antarmuka percakapan dan akses informasi yang lebih intuitif.
b) Kemudahan dalam mengakses data kompleks secara cepat tanpa harus menelusuri banyak layar atau menu.
c) Dukungan yang lebih baik untuk berbagai tipe pengguna baik staf teknis maupun pengguna non-teknis dengan penyajian informasi yang lebih mudah dipahami.

### 4.5 Nilai Strategis

a) Pemanfaatan data dari GLPI dan SCCM melalui analisis yang terintegrasi sehingga menghasilkan insight operasional yang lebih jelas dan relevan.
b) Membangun fondasi arsitektur yang dapat dikembangkan lebih lanjut untuk mendukung penggunaan AI lainnya di masa depan.

Dengan pendekatan berbasis data, inisiatif ini diharapkan membantu operasional TI di PT Astra Honda Motor bergerak menuju model yang lebih prediktif. Hal ini penting untuk meningkatkan kualitas pengambilan keputusan, mempercepat respons terhadap isu operasional, serta mengoptimalkan pemanfaatan sumber daya dalam pengelolaan infrastruktur TI.

---

## 5. Rekomendasi Solusi

Dengan tujuan yang ada, direkomendasikan untuk dilakukan aktivitas yang akan dibagi menjadi 2 (dua) fase:

- **Fase pertama**: migrasi sistem GLPI untuk mencapai tujuan yang diharapkan.
- **Fase kedua**: pengembangan kapabilitas AI pada sistem GLPI, dengan pendekatan **plugin-based AI architecture** yang didukung oleh **separate AI engine** berbasis framework orkestrasi AI. Pendekatan ini memungkinkan integrasi AI dilakukan tanpa mengubah atau mengganggu core system GLPI.

Dalam model ini, GLPI tetap berfungsi sebagai aplikasi utama yang mengelola proses operasional, antarmuka pengguna, serta kontrol akses. Sementara itu, proses komputasi AI dijalankan oleh AI service layer terpisah yang bertanggung jawab terhadap orkestrasi agen, pemrosesan workflow AI, serta interaksi dengan model AI.

Struktur arsitektur yang direkomendasikan mencakup beberapa komponen utama berikut:

a) **GLPI AI foundation** — layer konfigurasi dan governance untuk mengatur penggunaan AI, termasuk pengelolaan permissions, audit trail, serta kontrol akses terhadap fitur AI.
b) **AI orchestration engine** berbasis framework orkestrasi AI — menjalankan workflow AI, mengelola agent behavior, serta menangani proses reasoning dan model interaction.
c) **GLPI plugins** — menyediakan titik integrasi di dalam aplikasi GLPI untuk fitur seperti conversational assistance dan asset health analysis.

Dengan struktur ini, implementasi AI dapat dilakukan secara lebih terkontrol karena komponen AI berada di luar core platform. Selain itu, pengembangan atau penambahan kapabilitas AI di masa depan dapat dilakukan secara lebih fleksibel tanpa mempengaruhi stabilitas sistem GLPI yang sudah berjalan.

### 5.1 Migrasi Sistem GLPI (Fase Pertama)

#### 5.1.1 Fungsi Migrasi

Migrasi sistem GLPI dari versi 9.4.4 ke versi 11 dilakukan untuk memitigasi risiko keamanan pada infrastruktur CentOS 7, PHP 7.3, dan MariaDB 10.4 yang telah mencapai fase **End of Life (EOL)**. Menggunakan script upgrade bawaan GLPI versi terbaru, risiko kegagalan upgrade dan kehilangan data dapat diminimalisir.

Selain itu, deployment server baru dilakukan dengan memisahkan database dan aplikasi ke server yang berbeda agar utilisasi resource lebih optimal dan proses maintenance (seperti backup atau tuning DB) bisa independen dan tidak mengganggu satu sama lain.

**Perbandingan Komponen Server:**

| Komponen | Eksisting | Rekomendasi Target | Alasan & Justifikasi Rekomendasi |
|---|---|---|---|
| Sistem Operasi | CentOS 7 (EOL) | Rocky Linux 9 | Merupakan RHEL-like dengan security support hingga Mei 2032. |
| Web Server | Apache / Nginx lama | Apache / Nginx latest | Penyesuaian dengan OS target. |
| Database | MariaDB 10.4 (EOL) | MariaDB 11.4 LTS | Versi LTS memiliki security support hingga 2029. |
| PHP | PHP 7.3 (EOL) | PHP 8.4 | PHP 8.4 memiliki performa lebih baik dengan security support hingga 2028. |
| GLPI Core | Versi 9.4.4 | Versi 11.0.6 | Versi terbaru dari GLPI. |

#### 5.1.2 Hasil yang Diharapkan

Harapannya setelah migrasi dilakukan tercapai hasil berikut:

a) Sistem GLPI berjalan di server baru dengan performa yang lebih responsif.
b) Data aset, tiket, dan pengguna historis dari server lama (GLPI 9.4.4) berhasil dimigrasikan 100% ke GLPI 11.0.6.
c) Plugin eksisting telah disesuaikan dengan infrastruktur baru (baik di-upgrade maupun digantikan oleh fitur built-in).
d) Sistem terbebas dari vulnerability environment lama, yaitu OS CentOS 7, PHP 7.3, serta MariaDB 10.4.

#### 5.1.3 Mekanisme Migrasi yang Diajukan

Mengingat jarak versi yang cukup jauh antara GLPI 9.4.4 dan 11.0.6, terdapat perbedaan pada persyaratan infrastruktur pendukung, yaitu pada bagian minimum versi PHP dan MariaDB serta arsitektur struktur database. Script upgrade bawaan GLPI secara komprehensif mendukung proses upgrade dari versi lama di atas 0.85 dengan menjalankan patch inkremental secara otomatis.

Meskipun OS pada server existing mendukung versi minimum PHP dan MariaDB yang dibutuhkan GLPI 11, status OS CentOS 7 yang sudah EOL membuat proses upgrade pada server eksisting sangat tidak disarankan.

Strategi terbaik adalah menyiapkan infrastruktur baru secara paralel, menggunakan versi yang masih memiliki dukungan panjang (LTS): **Rocky Linux 9, PHP 8.4, dan MariaDB 11.4**.

Data dari server lama akan diekspor dan di-deploy ke server baru, kemudian script upgrade GLPI 11 dijalankan untuk memproses pembaruan versi. Setelah core upgrade selesai, tahapan paling krusial adalah mengeksekusi serangkaian post-upgrade scripts (via console CLI) untuk mengonversi data GLPI lama ke format modern yang dianjurkan oleh versi terbaru.

Berdasarkan strategi tersebut, alur kerja (workflow) migrasi dibagi menjadi beberapa fase:

**Fase Sandbox**

Fase ini merupakan tahap penyiapan infrastruktur baru, simulasi upgrade (dry-run), dan pengujian sistem secara menyeluruh tanpa mengganggu sistem produksi saat ini.

a) Assessment keseluruhan pada sistem dan arsitektur database eksisting.
b) Perancangan arsitektur deployment yang baru (pemisahan App dan Database).
c) Menyiapkan 2 (dua) Virtual Machine (VM) baru, yaitu VM Aplikasi dan VM Database menggunakan OS Rocky Linux 9.x.
d) Instalasi serta tuning MariaDB 11.4 LTS di VM Database.
e) Instalasi PHP 8.4 dan konfigurasi Web Server di VM Aplikasi.
f) Melakukan Export/Dump database GLPI 9.4.4 dari Server Produksi eksisting, lalu di-import ke VM Database baru.
g) Direktori `files/` (dokumen, gambar, plugins) disalin dan disinkronisasi ke VM Aplikasi baru.
h) Mengeksekusi script upgrade GLPI versi 11.0.6 melalui Command Line Interface (CLI) di VM Aplikasi. Script ini secara otomatis memproses lompatan inkremental dari versi 9.4.x melewati 9.5.x, 10.0.x, hingga 11.0.x.
i) Mengeksekusi Post-Upgrade Scripts (Migrasi Format Data) — tahapan wajib untuk memodernisasi arsitektur database, meliputi:
   - **Timezones Migration**: mengubah format waktu menjadi timestamp.
   - **Charset Migration**: mengubah karakter set database dari utf8mb3 ke format modern utf8mb4.
   - **Unsigned Keys Migration**: memigrasikan struktur tabel relasional untuk menggunakan unsigned integers demi performa dan efisiensi ruang penyimpanan.
j) Instalasi plugin File Injection, Objects, dan Additional Fields dengan versi terbaru yang kompatibel dengan GLPI 11.0.x.
k) Melakukan migrasi Plugin Objects ke fitur bawaan GLPI 11.0.
l) Melakukan verifikasi data historis aset dan konfigurasi sistem.
m) Dilakukan System Integration Testing (SIT) dan User Acceptance Testing (UAT) bersama user, termasuk pendampingan pengujian pembuatan tiket/aset di environment baru.

**Fase Cut-off**

Fase ini adalah tahap eksekusi akhir saat jadwal Cut-Over telah disepakati bersama. Sistem produksi lama akan memasuki masa downtime (Read-Only/Offline) untuk memastikan tidak ada input data baru yang tertinggal. Pada prinsipnya, fase ini mengulangi alur dump dan eksekusi script seperti pada Fase Sandbox, namun prosesnya jauh lebih cepat karena server baru sudah terkonfigurasi.

a) Pengumuman downtime dan penutupan akses ke server produksi eksisting.
b) Melakukan Export/Dump database final dari Server Produksi untuk mendapatkan data paling baru.
c) Melakukan import database final tersebut ke VM Database baru (menimpa data Sandbox sebelumnya).
d) Men-sinkronisasi ulang (rsync delta) folder `files/` dari server produksi ke VM Aplikasi baru untuk menarik lampiran file yang baru diunggah.
e) Menjalankan kembali eksekusi Upgrade Script GLPI 11.0.6 dan ketiga perintah Post-Upgrade Scripts (Timestamp, Charset utf8mb4, dan Unsigned Keys) di server baru.
f) Shutdown server eksisting agar IP dapat digunakan oleh server baru.
g) Pembaruan konfigurasi jaringan IP VM Aplikasi Baru menggunakan IP Server Eksisting agar sistem resmi GO LIVE.
h) Observasi stabilitas aplikasi jaringan pasca Cut-off sebelum dilakukan Serah Terima (Handover) akhir.

**Fase New Production**

Fase ini dilakukan setelah seluruh aktivitas migrasi sudah dilakukan. Pada fase ini perlu dilakukan verifikasi data GLPI hasil dari Cut-Off yang sudah dilakukan bersama tim PT Astra Honda Motor untuk memastikan data sudah sesuai dengan ekspektasi.

![Gambar 5.1 Workflow Migrasi GLPI](images/gambar-5.1-workflow-migrasi.jpeg)
*Gambar 5.1 Workflow Migrasi GLPI*

#### 5.1.4 System Requirement

##### 5.1.4.1 Kebutuhan Infrastruktur (Virtual Machine)

Diperlukan 2 Virtual Machine sesuai dengan rencana yang sudah dipaparkan di atas, dengan detail sebagai berikut:

**a) VM 1 — Aplikasi Web GLPI (New Deployment)**
- Fungsi: Menjalankan Web Server (Apache/Nginx) dan PHP 8.4.
- CPU: 8 vCPU
- RAM: 8 GB
- Storage: 100 GB sebagai Disk OS dan 500 GB sebagai Disk Data
- OS: Rocky Linux 9.7

**b) VM 2 — Database MariaDB (New Deployment)**
- Fungsi: Menjalankan database MariaDB 11.4 LTS.
- CPU: 4 vCPU
- RAM: 8 GB
- Storage: 100 GB sebagai Disk OS dan 500 GB sebagai Disk Data
- OS: Rocky Linux 9.7

##### 5.1.4.2 Kebutuhan Jaringan & Keamanan

**a) IP Address:** 2 IP Address statis (Local/Private) untuk kedua server New Deployment baru.

**b) Firewall Rules:**
- VM Aplikasi: Mengizinkan port HTTP (80) dan HTTPS (443).
- VM Database: Mengizinkan port TCP 3306 hanya dari IP VM Aplikasi.
- Port SSH (22) pada kedua VM untuk akses masuk.

##### 5.1.4.3 Kebutuhan DNS & Domain

a) Domain: alokasi hostname baru untuk kedua New Deployment.

##### 5.1.4.4 Kebutuhan Hak Akses & Credential

a) Server Lama & Clone (CentOS 7): Akses User sudoer via SSH.
b) Database Lama: Kredensial user yang memiliki akses ke database eksisting.

### 5.2 Ekstensi AI (Fase Kedua)

#### 5.2.1 Fitur

##### 5.2.1.1 Fitur Chat AI

**5.2.1.1.1 Fungsi Fitur Chat AI**

Fitur ini berfungsi untuk menambahkan asisten conversational di dalam GLPI untuk membantu pengguna maupun staf IT dalam mengambil informasi, merangkum data yang ada, dan menentukan tindakan lanjutan secara cepat.

Alih-alih membuka banyak halaman dan melakukan filter secara manual, Chat AI dapat digunakan untuk memberikan jawaban ringkas yang berbasis pada konteks operasional terkait.

User experience sepenuhnya dilakukan di GLPI. Sementara itu, proses AI berjalan di belakang layar menggunakan engine berbasis framework orkestrasi AI yang berfungsi untuk mengatur alur kerja AI. Engine ini mengorkestrasi berbagai proses AI dan menjalankan fungsi tertentu melalui tools, termasuk melakukan query ke database informasi GLPI.

**5.2.1.1.2 Hasil yang Diharapkan**

a) Mengurangi waktu yang dibutuhkan untuk mencari informasi di berbagai data dan parameter yang tersebar di sistem GLPI.
b) Mengoptimalkan pemanfaatan data operasional yang sebelumnya sudah tersimpan di GLPI agar bisa digunakan kembali secara lebih efektif.
c) Menghasilkan rekomendasi dan panduan solusi teknis yang lebih konsisten sehingga dapat digunakan secara selaras di seluruh level operasional dalam organisasi.

**5.2.1.1.3 Nilai Strategis**

Bagi PT Astra Honda Motor, sistem Chat AI dapat dimanfaatkan tidak hanya sekadar chatbot biasa. Fungsinya lebih luas, yaitu sebagai layer produktivitas tambahan yang terintegrasi dengan sistem service management yang sudah ada.

Dengan kata lain, AI ini dirancang untuk membantu meningkatkan kecepatan pemrosesan informasi, dan skalabilitas operasional. Ia bekerja berdampingan dengan data dan proses yang sudah ada di sistem sebelumnya, bukan menggantikannya.

Implementasinya diharapkan dapat membantu meningkatkan kinerja unit kerja melalui berbagai kemampuan perbaikan berikut:

a) Menjawab pertanyaan operasional dengan mengakses data yang relevan melalui mekanisme akses yang terkontrol, menggunakan tools yang sudah disetujui untuk mengambil informasi dari database GLPI yang terotorisasi.
b) Memastikan riwayat siklus hidup setiap aset tercatat dan dapat dilacak dengan jelas.

**5.2.1.1.4 Contoh Interaksi AI**

Ilustrasi respons yang ditampilkan di dalam antarmuka Chat AI dapat berupa sebagai berikut:

**Chat Query:**
> "Susun ringkasan mengenai aset LAP-1042, meliputi penetapan alokasi pengguna, laporan insiden mutakhir yang sedang berlangsung, pemantauan masa pertanggungan asuransi perbaikan (warranty), dan deteksi terhadap segala pertanda potensi risiko kesehatan fungsional parameter operasional utilitas (health risk indicators) terkini."

**Respons:**
> "Perangkat aset komputasi dengan kode LAP-1042 saat ini tercatat digunakan oleh Lukman di unit Finance. Dalam periode 90 hari terakhir, perangkat tersebut tercatat terkait dengan tiga support ticket. Dua tiket berkaitan dengan penurunan performa sistem, sementara satu tiket melaporkan degradasi kondisi baterai (battery health). Selain itu, masa garansi perangkat akan berakhir dalam waktu sekitar empat bulan dari kondisi saat ini. Berdasarkan riwayat tiket, indikasi penurunan performa yang berulang, serta tanda-tanda penuaan baterai, perangkat ini menunjukkan tingkat risiko kesehatan operasional pada level moderat (moderate health risk). Kondisi ini menunjukkan adanya potensi gangguan operasional jika tidak ditangani lebih lanjut. Sebagai tindak lanjut, disarankan untuk menjadwalkan proactive maintenance guna melakukan pemeriksaan dan perbaikan preventif. Selain itu, perangkat ini juga dapat mulai dipertimbangkan dalam perencanaan refresh atau penggantian perangkat dalam horizon waktu dekat sebagai bagian dari pengelolaan asset lifecycle."

**5.2.1.1.5 Ilustrasi Interaksi AI**

Cara kerja Chat AI dapat dijelaskan sebagai proses yang terstruktur untuk menghasilkan respons yang berbasis data. Alurnya secara umum adalah sebagai berikut:

a) Pengguna mengajukan pertanyaan melalui antarmuka GLPI.
b) Plugin GLPI menerima pertanyaan dan diteruskan ke AI engine.
c) Engine berbasis framework orkestrasi AI memproses permintaan, lalu menentukan tools yang sesuai untuk digunakan dalam menjawab pertanyaan tersebut.
d) Tools yang dipilih mengambil data yang relevan dari GLPI atau sumber data lain yang telah diotorisasi. Jika diperlukan, sistem juga menambahkan konteks tambahan yang relevan untuk membantu analisis.
e) AI kemudian menyusun hasilnya, yang dapat berupa:
   - Jawaban atas pertanyaan operasional
   - Ringkasan informasi
   - Rekomendasi langkah atau tindakan yang dapat dilakukan
f) Plugin GLPI menyiapkan hasil untuk ditampilkan, termasuk:
   - Menyusun format tampilan agar mudah dibaca
   - Mencatat aktivitas dalam log sistem
   - Menjalankan proses approval jika memang diperlukan sebelum hasil ditampilkan ke pengguna

Pendekatan ini memastikan bahwa respons yang dihasilkan berbasis data yang valid dan terotorisasi, bukan sekadar hasil respons dari AI.

##### 5.2.1.2 Fitur Asset Health AI dengan Korelasi SCCM

**5.2.1.2.1 Fungsi Fitur Asset Health AI**

Fitur AI ini berjalan di belakang sistem untuk menganalisis kesehatan aset dan memberikan rekomendasi ke depan dengan memanfaatkan korelasi data antara GLPI dan Microsoft System Center Configuration Manager (SCCM).

Data aset dari GLPI digabungkan dengan data operasional Windows dari SCCM untuk menemukan pola anomali atau masalah yang sulit terdeteksi secara manual, terutama pada lingkungan dengan jumlah aset yang besar. Tujuannya adalah mengubah pendekatan dari asset management yang hanya bersifat deskriptif menjadi lebih prediktif dan mendukung pengambilan keputusan.

Kapabilitas ini dijalankan melalui modul terpisah yang menggunakan engine berbasis framework orkestrasi AI. Engine ini dirancang untuk menangani workflow analisis yang lebih panjang dan kompleks, termasuk:

a) Menjalankan beberapa tahap analisis data secara berurutan.
b) Mengorkestrasi pemanggilan berbagai komponen analitik yang diperlukan.
c) Menggabungkan hasil dari beberapa proses analisis menjadi satu kesimpulan terpadu.
d) Menghasilkan output yang terstruktur untuk ditampilkan kembali di GLPI.

Hasil analisis tersebut kemudian dapat ditinjau oleh manajemen sebagai bagian dari proses review yang terkontrol, sebelum diputuskan tindakan operasional yang perlu dilakukan.

**5.2.1.2.2 Hasil yang Diharapkan**

a) Deteksi lebih awal terhadap penurunan kondisi aset (declining asset health).
b) Visibilitas yang lebih jelas terhadap perangkat atau model yang sering mengalami masalah berulang.
c) Prioritas tindakan operasional menjadi lebih jelas dan terarah bagi tim teknis.

#### 5.2.2 Konsep Arsitektur AI

Arsitektur yang direkomendasikan dibangun dalam dua layer utama yang saling terintegrasi:

a) **GLPI Plugin Layer** — bertanggung jawab menyediakan user interface, pengaturan access control, konfigurasi sistem, serta integrasi dengan proses bisnis yang berjalan di dalam environment GLPI. Plugin ini juga menjadi titik masuk penggunaan fitur AI bagi pengguna sistem.
b) **Separate AI Engine** berbasis framework orkestrasi AI — menangani proses pemrosesan AI seperti agent orchestration, eksekusi long-running workflows, serta pengelolaan logika AI.

Dalam pendekatan ini, GLPI tetap berfungsi sebagai system of record dan menjadi aplikasi utama yang sepenuhnya berada dalam kontrol operasional. Sementara itu, framework orkestrasi AI tidak menggantikan peran GLPI, tetapi berfungsi sebagai runtime layer yang menjalankan proses analisis dan automasi berbasis AI dengan memanfaatkan tools yang telah disetujui serta antarmuka yang memungkinkan akses terotorisasi ke data GLPI dan layanan eksternal yang disediakan oleh pihak PT Astra Honda Motor.

#### 5.2.3 Arsitektur Flow AI

Diagram berikut menunjukkan bagaimana fitur AI terintegrasi dengan sistem GLPI. Pengguna berinteraksi melalui web interface GLPI, kemudian permintaan tersebut diteruskan ke GLPI AI plugin yang berfungsi sebagai penghubung antara GLPI dan AI Engine berbasis framework orkestrasi AI.

Setelah menerima permintaan, AI Engine menjalankan workflow dan agents untuk memprosesnya. Proses ini menggunakan LLM services yang telah disetujui atau model yang di-host oleh pihak PT Astra Honda Motor. Dalam menjalankan analisis, AI dapat mengakses data dari GLPI maupun SCCM melalui endpoint yang telah disetujui dan diotorisasi.

Hasil pemrosesan kemudian dikembalikan dalam bentuk structured output ke GLPI AI plugin, dan ditampilkan kembali pada web interface GLPI sehingga dapat langsung dibaca oleh pengguna.

![Gambar 5.2 Arsitektur Flow AI](images/gambar-5.2-arsitektur-flow-ai.jpeg)
*Gambar 5.2 Alur integrasi AI pada sistem GLPI yang memanfaatkan framework orkestrasi AI, service LLM yang disetujui, serta data GLPI dan SCCM untuk menghasilkan output AI yang terstruktur bagi pengguna.*

#### 5.2.4 Sequence Diagram AI

Diagram ini menggambarkan alur interaksi ketika pengguna GLPI menggunakan fitur AI. Proses dimulai saat pengguna mengirimkan pertanyaan atau permintaan melalui antarmuka web GLPI. Permintaan tersebut diteruskan ke plugin AI pada GLPI, yang terlebih dahulu menerapkan aturan konfigurasi, hak akses, dan pencatatan aktivitas.

Setelah itu, permintaan dikirim ke AI Engine berbasis framework orkestrasi AI untuk diproses. Engine akan menggunakan LLM yang telah disetujui untuk memahami permintaan dan menentukan langkah selanjutnya.

Data yang diperoleh kemudian digunakan untuk menghasilkan jawaban atau rekomendasi yang terstruktur, yang dikirim kembali ke plugin AI dan ditampilkan kepada pengguna melalui antarmuka GLPI.

![Gambar 5.3 Sequence Diagram AI](images/gambar-5.3-sequence-diagram-ai.jpeg)
*Gambar 5.3 Alur interaksi pengguna GLPI dengan sistem AI untuk menghasilkan jawaban atau rekomendasi berbasis data GLPI dan SCCM.*

#### 5.2.5 Tech Stack AI

Pemilihan technology stack solusi ini didefinisikan sebagai berikut:

**5.2.5.1 GLPI in-platform experience**
Menggunakan GLPI 11, PHP 8.2+, Twig, serta komponen UI dan Javascript bawaan GLPI. Tujuannya adalah menyediakan pengalaman pengguna yang sepenuhnya terintegrasi di dalam GLPI, mencakup halaman konfigurasi dan titik masuk interaksi AI yang mengikuti aturan aplikasi GLPI.

**5.2.5.2 Plugin business logic**
Menggunakan GLPI plugin framework, controllers, services, cron tasks, serta model keamanan bawaan platform. Komponen ini bertanggung jawab menangani logika aplikasi seperti persiapan request, serta penyajian hasil tanpa melakukan modifikasi pada core GLPI.

**5.2.5.3 AI service API**
Menggunakan Python 3.11+, FastAPI atau framework Python web setara, dengan validasi skema seperti Pydantic. Berfungsi menyediakan endpoint API antara GLPI dan AI engine untuk kebutuhan chat, perangkuman, rekomendasi, serta workflow yang berjalan dalam durasi panjang.

**5.2.5.4 AI orchestration runtime**
Menggunakan framework orkestrasi AI, service orkestrasi berbasis Python, serta structured tool wrappers. Berfungsi mengoordinasikan alur kerja AI, pembuatan respons, percabangan workflow, serta checkpoint untuk proses human review.

**5.2.5.5 Background processing**
Memanfaatkan Python worker dengan mekanisme eksekusi berbasis queue seperti Celery, yang dapat didukung oleh Redis sebagai message broker. Pendekatan ini digunakan untuk menjalankan proses yang membutuhkan waktu eksekusi lebih lama, seperti analisis asset health, pemrosesan tugas tertunda, serta berbagai pekerjaan yang tidak perlu dijalankan langsung dalam siklus request–response aplikasi.

**5.2.5.6 Model integration**
Menggunakan API LLM internal atau gateway model milik PT Astra Honda Motor. Layer ini menjaga fleksibilitas penggunaan model AI tanpa mengubah struktur runtime solusi.

**5.2.5.7 Data access and tools**
Menggunakan endpoint tools GLPI yang terkelola, konektor SCCM, serta service normalisasi dan pemetaan data. Berfungsi untuk mengambil data GLPI dan SCCM yang telah diotorisasi, mengubahnya menjadi input terstruktur, dan menyediakan dasar data yang valid untuk menghasilkan respons AI yang akurat dan dapat diaudit.

**5.2.5.8 Deployment**
Menggunakan Docker sebagai mekanisme deployment untuk memisahkan service AI engine dengan system GLPI. Dengan pendekatan ini, komponen AI dapat di-scale, dikonfigurasi, dan ditingkatkan tanpa mempengaruhi stabilitas platform GLPI.

---

## 6. Scope Of Work (SOW)

Berikut merupakan cakupan pekerjaan dari solusi yang ditawarkan pada proposal ini.

### 6.1 Migrasi Sistem GLPI

a) Melakukan assessment awal terhadap lingkungan server eksisting.
b) Instalasi dan konfigurasi dasar Sistem Operasi (Rocky Linux 9), Web Server, PHP 8.3, dan MariaDB 11.4 LTS pada VM baru yang telah disediakan User.
c) Eksekusi upgrade GLPI dari versi 9.4.4 → 11.0.x.
d) Pemisahan infrastruktur monolitik eksisting menjadi arsitektur two-tier (Server Aplikasi dan Server Database dipisah).
e) Migrasi as-is 100% data tiket, histori aset, pengguna, konfigurasi LDAP/SSO eksisting, dan file lampiran (`files/`).
f) Instalasi 2 plugin utama (Additional Fields, File Injection) dan migrasi 1 Plugin Objects Management.
g) Sinkronisasi ulang data (rsync) saat fase Cut-off.
h) Pendampingan User Acceptance Testing (UAT) dan serah terima (Handover).

### 6.2 Ekstensi AI

a) Pengembangan fitur kecerdasan buatan yang terintegrasi ke dalam GLPI melalui mekanisme plugin, dengan dukungan AI engine berbasis framework orkestrasi AI yang berjalan sebagai service terpisah.
b) Penyediaan kemampuan conversational interface yang memungkinkan pengguna GLPI dan staf operasional IT berinteraksi dengan sistem secara lebih intuitif untuk memperoleh informasi maupun insight operasional.
c) Pemanfaatan analitik untuk menilai kondisi asset health serta menghasilkan rekomendasi berdasarkan korelasi data antara GLPI dan informasi perangkat dari SCCM.
d) Penerapan layer AI orchestration yang memastikan proses seperti data querying, summarization, dan eksekusi automated workflows dapat berjalan secara terkendali melalui penggunaan tools yang telah diotorisasi.

### 6.3 Timeline Pengerjaan

Adapun untuk mengimplementasikan solusi-solusi tersebut dibutuhkan waktu sesuai estimasi timeline berikut ini.

![Gambar 6.1 Estimasi Timeline Fase Pertama (Migrasi GLPI) dan Fase Kedua (Ekstensi AI)](images/gambar-6.1-timeline-fase1.jpeg)
*Gambar 6.1 Estimasi timeline Fase Pertama (Migrasi GLPI) — Gambar 6.2 Estimasi Timeline Fase Kedua (Ekstensi AI)*

**Rincian Aktivitas Migrasi GLPI** (lihat juga diagram Gantt lengkap pada gambar di bawah untuk pemetaan minggu per bulan):

| No | Environment | Aktivitas | Durasi (Hari) | PIC |
|---|---|---|---|---|
| 1 | Sandbox | Backup config, files, and plugin directories | 1 | STI |
| 2 | Sandbox | Dump Database | 1 | AHM & STI |
| 3 | Sandbox | Install Rocky 9.7 | — | STI |
| 4 | Sandbox | Install PHP 8.4 | — | STI |
| 5 | Sandbox | Install MariaDB 11.4 | — | STI |
| 6 | Sandbox | Install Webserver Nginx/Apache | — | STI |
| 7 | Sandbox | Config Network & Web Server using Temp | — | AHM & STI |
| 8 | Sandbox | Download & Extract GLPI 11.0 | — | STI |
| 9 | Sandbox | Restore backed up config, files, and plugin directories | — | STI |
| 10 | Sandbox | Restore database | — | STI |
| 11 | Sandbox | Move `glpi/config/` → `/etc/glpi/` dan set permission | — | STI |
| 12 | Sandbox | Move `glpi/files/` → `/var/lib/glpi/files/` dan set permission | — | STI |
| 13 | Sandbox | Create dir `/var/log/glpi` dan set permission | — | STI |
| 14 | Sandbox | Create `/var/www/glpi/inc/downstream.php` | — | STI |
| 15 | Sandbox | Run `php bin/console system:check_requirements` | — | STI |
| 16 | Sandbox | Run `php bin/console database:check_schema_integrity` | — | STI |
| 17 | Sandbox | Run `php bin/console db:update` | — | STI |
| 18 | Sandbox | Download & extract latest field, data injection & generic object plugin | — | STI |
| 19 | Sandbox | Run `php bin/console migration:genericobject_plugin_to_core` | — | STI |
| 20 | Sandbox | Remove Generic Object plugin (deprecated) | — | STI |
| 21 | Sandbox | Run `php bin/console migration:timestamps` | — | STI |
| 22 | Sandbox | Run `php bin/console migration:utf8mb4` | — | STI |
| 23 | Sandbox | Run `php bin/console migration:unsigned_keys` | — | STI |
| 24 | Sandbox | Data verification | 3 | AHM |
| 25 | Sandbox | Remove Sandbox GLPI 11 files & db | — | STI |
| 26 | Old Production | Download & Extract GLPI 11.0 | — | STI |
| 27 | Old Production | Stop httpd Production | — | AHM & STI |
| 28 | Old Production | Backup config, files, and plugin directories GLPI Prod | — | AHM & STI |
| 29 | Old Production | Dump Database Existing | — | AHM |
| 30 | New Production | Restore backed up config, files, and plugin directories | — | STI |
| 31 | New Production | Restore database | — | STI |
| 32 | New Production | Move `glpi/config/` → `/etc/glpi/` dan set permission | — | STI |
| 33 | New Production | Move `glpi/files/` → `/var/lib/glpi/files/` dan set permission | — | STI |
| 34 | New Production | Create dir `/var/log/glpi` dan set permission | — | STI |
| 35 | New Production | Create `/var/www/glpi/inc/downstream.php` | — | STI |
| 36 | New Production | Run `php bin/console system:check_requirements` | — | STI |
| 37 | New Production | Run `php bin/console database:check_schema_integrity` | — | STI |
| 38 | New Production | Run `php bin/console db:update` | — | STI |
| 39 | New Production | Download & extract latest field, data injection & generic object plugin | — | STI |
| 40 | New Production | Run `php bin/console migration:genericobject_plugin_to_core` | — | STI |
| 41 | New Production | Remove Generic Object plugin (deprecated) | — | STI |
| 42 | New Production | Run `php bin/console migration:timestamps` | — | STI |
| 43 | New Production | Run `php bin/console migration:utf8mb4` | — | STI |
| 44 | New Production | Run `php bin/console migration:unsigned_keys` | — | STI |
| 45 | New Production | Shutdown Old Production VM | — | AHM & STI |
| 46 | New Production | Config Network (change to Existing Prod IP) | — | STI |
| 47 | New Production | Data Verification | 3 | AHM |
| 48 | New Production | Testing | 1 | AHM & STI |
| 49 | New Production | Documentation | 10 | STI |

> Catatan: kolom Durasi hanya tercatat eksplisit pada beberapa baris di dokumen sumber; sebagian besar aktivitas ditampilkan sebagai blok pada Gantt chart tanpa angka durasi tertulis. Untuk pemetaan minggu-per-minggu yang presisi, rujuk gambar Gantt chart berikut:

![Gambar 6.2 Detail Timeline Migrasi GLPI](images/gambar-6.2-timeline-detail.jpeg)
*Gambar 6.2 Detail Gantt chart timeline migrasi GLPI (Sandbox, Old Production, New Production)*

---

## 7. Out of Scope (OOS)

Hal-hal berikut berada di luar cakupan dari dokumen proposal ini, kecuali terdapat kesepakatan terpisah, antara lain:

### 7.1 Migrasi Sistem GLPI

a) Penyediaan Infrastruktur seperti perangkat keras fisik, lisensi Hypervisor atau service penyewaan Cloud.
b) Lisensi sistem operasi, maupun framework dan runtime.
c) Konfigurasi infrastruktur Core PT Astra Honda Motor.
d) Pembuatan sertifikat SSL dan setting pada firewall hardware.
e) Perubahan data / Data Cleansing; data dimigrasikan apa adanya (as-is).
f) Modifikasi kode inti (hardcode core system) GLPI di luar standar official demi kompatibilitas keamanan jangka panjang.
g) Modifikasi surrounding apps yang related dengan GLPI (semisal B2E).
h) Akses dan expertise ke surrounding apps, testing komposit integrasi surrounding apps.
i) Testing di surrounding Apps di luar GLPI (jika diperlukan menjadi tanggung jawab AHM).
j) Troubleshoot di surrounding Apps di luar GLPI (jika diperlukan menjadi tanggung jawab AHM).
k) Instalasi atau modifikasi Plugin setelah migrasi dilakukan.
l) Modifikasi Source Code GLPI.
m) Vulnerability Testing.
n) Bug Fixing dan Vulnerability Fixing GLPI yang tidak tercover oleh Source Code GLPI.

### 7.2 Ekstensi AI

a) Hosting, operasional dan support untuk self-hosted LLM platform.
b) Sizing model, tuning model, deployment dan konfigurasi RAG, provisioning GPU, monitoring platform, backup, patching, dan management ketersediaan service AI di-host PT Astra Honda Motor.
c) Tanggung jawab terhadap performa, keamanan, lisensi, dan kontinuitas layanan LLM milik PT Astra Honda Motor.
d) Tanggung jawab atas performa, keamanan, lisensi dan kontinuitas dari SCCM PT Astra Honda Motor.
e) Penyiapan, validasi, dan support untuk koneksi ke SCCM, mencakup akses jaringan, kredensial, API access, database access, firewall rules, dan prasyarat konektivitas di sisi PT Astra Honda Motor.
f) Administrasi platform SCCM, maintenance, troubleshooting, upgrade management, atau perbaikan kualitas data yang dilakukan di dalam sistem SCCM.
g) Data governance tingkat enterprise, berada di luar ruang lingkup plugin AI untuk GLPI, termasuk kegiatan seperti program pembersihan data besar-besaran pada sistem sumber (source-system cleanup).
h) Desain ulang dalam skala besar di luar kapabilitas AI yang diusulkan.
i) Instalasi atau modifikasi plugin yang tidak berkaitan dengan goal dari project ekstensi AI.
j) Modifikasi Source Code GLPI.
k) Vulnerability Testing.
l) Bug Fixing dan Vulnerability Fixing GLPI yang tidak tercover oleh Source Code GLPI.

---

## 8. Kesimpulan

Implementasi yang diusulkan mencakup dua aspek utama, yaitu peningkatan versi platform GLPI dari versi lama menuju versi yang lebih modern serta pengenalan kapabilitas analisis berbasis AI yang terintegrasi dengan sistem tersebut. Proses upgrade dari GLPI versi 9 ke versi 11 bertujuan memastikan sistem berada pada platform yang lebih mutakhir.

Setelah fondasi sistem diperbarui, direkomendasikan untuk melakukan ekstensifikasi AI melalui pendekatan plugin dan service layer terpisah. Dengan pendekatan ini, GLPI tetap berfungsi sebagai system of record yang mengelola data operasional seperti tickets, assets, knowledge, dan inventory, sementara komponen AI bertugas membantu proses analisis data, otomasi alur kerja, serta penyediaan rekomendasi berbasis konteks operasional.

Pemisahan peran antara platform GLPI dan service AI juga memberikan fleksibilitas dalam pengembangan, pengelolaan, serta pengendalian sistem. AI dapat dikembangkan atau diperluas tanpa mempengaruhi stabilitas sistem inti GLPI, sementara tata kelola akses, auditabilitas, dan kontrol operasional tetap berada di dalam platform utama.

Melalui pendekatan ini, PT Astra Honda Motor dapat memanfaatkan data operasional yang sudah tersedia untuk menghasilkan insight yang lebih cepat dan relevan, meningkatkan efisiensi operasional layanan IT, serta mendukung pengambilan keputusan yang lebih berbasis data. Implementasi ini diharapkan menjadi langkah strategis dalam memperkuat pengelolaan layanan IT sekaligus membuka peluang pengembangan kapabilitas analitik dan otomasi yang lebih luas di masa mendatang.

---

*Dokumen ini dikonversi dari file PDF sumber ke format Markdown untuk memudahkan pengembangan proyek. Diagram-diagram utama (workflow migrasi, arsitektur AI, sequence diagram, dan timeline) disertakan sebagai gambar pada folder `images/` di samping file ini.*
