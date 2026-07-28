# Review Revisi: CONTEXT.md, PLAN.md, SPEC.md (Iterasi ke-2)

Saya sudah membandingkan versi revisi dengan draft sebelumnya serta proposal PDF. Kabar baik dulu: **seluruh 8 temuan prioritas tinggi/sedang dari review sebelumnya sudah diakomodasi** dengan baik dan konsisten di ketiga file. Namun proses revisi ini memunculkan **beberapa detail implementasi baru yang perlu dipertajam** sebelum coding, terutama seputar identitas approver, durability data governance, dan beberapa gap kecil antar-dokumen.

---

## 1. Verifikasi: Temuan Sebelumnya Sudah Terselesaikan ✅

| # | Temuan Sebelumnya | Status di Revisi |
|---|---|---|
| 1 | Versi SCCM tidak dikonfirmasi | ✅ Sudah ditandai eksplisit "*tergantung konfirmasi AHM*" di context.md §1 dan §4 poin 3 |
| 2 | Routing tidak mengakomodasi query gabungan | ✅ ADR-06 kini 4 kategori + `joint_analysis` dengan Orchestrator Manager Agent (context.md, spec.md §6) |
| 3 | Tidak ada human review/approval | ✅ ADR-08 + endpoint `/approve` `/reject` + field `review_status` |
| 4 | Dependency eksternal AHM belum tercermin | ✅ Section "Prasyarat & Dependency Eksternal" ditambahkan di plan.md dan context.md §4 |
| 5 | Risiko kualitas data matching | ✅ Blacklist serial placeholder, filter `IPEnabled0=1`, Stale Records Resolver (Task 4.2) |
| 6 | Skala data (bulk fetch) | ✅ `get_all_systems(batch_size, offset)` dengan cursor/pagination |
| 7 | Deployment (Docker, TLS) belum ada task | ✅ Task 1.4 docker-compose, ADR-02 TLS encrypt |
| 8 | Inkonsistensi `v_GS_PC_BIOS` | ✅ Sudah masuk tabel mapping context.md §3 |

Solid — struktur governance (ADR-08, ADR-09) dan data-quality handling sekarang selaras dengan komitmen proposal §5.2.1.2.1 dan §5.2.5.4.

---

## 2. Temuan Baru yang Perlu Diklarifikasi Sebelum Implementasi

### 🔴 2.1 Identitas Approver Tidak Jelas Dengan Skema Auth Saat Ini

ADR-09 mensyaratkan audit log mencatat `user_id/requester` untuk setiap aksi approve/reject. Namun Global Constraints di plan.md hanya menyebut:

> *"All management/correlation API endpoints protected by `GATEWAY_API_KEY` Bearer token"*

Ini adalah **satu shared secret**, bukan mekanisme autentikasi per-user. Dengan skema ini, endpoint `POST /{job_id}/approve` **tidak tahu siapa sebenarnya yang menekan tombol approve** — API Gateway hanya tahu bahwa pemanggil memiliki API key yang valid (kemungkinan besar dipanggil oleh GLPI plugin atas nama user manapun yang login).

**Rekomendasi:** Tentukan salah satu dari dua pendekatan berikut, lalu tuliskan eksplisit di spec.md §5:
- **Opsi A (lebih sederhana):** GLPI plugin (yang tahu identitas user login) wajib menyertakan `requester_id`/`requester_name` sebagai field di body request `/approve` dan `/reject`. AI Gateway hanya mempercayai (trust) identitas ini karena datang dari GLPI plugin yang sudah terautentikasi di sisi GLPI. Perlu dicatat sebagai asumsi keamanan (trust boundary).
- **Opsi B (lebih ketat):** AI Gateway memvalidasi identitas requester langsung ke GLPI REST API (session token forward) sebelum mencatat audit — lebih aman tapi menambah kompleksitas.

Tanpa keputusan ini, `user_id` di audit log berisiko selalu kosong/generic, sehingga tujuan compliance ADR-09 tidak tercapai secara substansi.

---

### 🔴 2.2 Durability Audit Log & Pending Review — Redis Saja Tidak Cukup

ADR-09 menyebut audit log disimpan *"di database/Redis"* — kata "atau" ini masih ambigu. Demikian pula spec.md §4 menyatakan hasil korelasi `pending_review` disimpan "di Redis" tanpa mekanisme persistence eksplisit.

**Risiko:** Redis secara default adalah in-memory cache. Jika:
- Container Redis restart tanpa `appendonly yes`/RDB snapshot yang dikonfigurasi, atau
- TTL key tidak diatur dengan tepat (atau justru diset TTL sehingga otomatis hilang),

maka **hasil korelasi yang masih `pending_review` bisa hilang sebelum sempat di-approve**, dan **audit trail (bukti kepatuhan) bisa hilang** — ini bertentangan langsung dengan tujuan ADR-09 sendiri (menjamin transparansi & kepatuhan audit).

**Rekomendasi:**
1. Audit log (trigger/approve/reject) sebaiknya **tidak** hanya di Redis — simpan di tabel database persisten (bisa reuse database aplikasi existing GLPI AI Gateway jika sudah ada, atau tabel baru `audit_log`). Redis cukup untuk *job status* sementara (progress tracking), bukan untuk *audit record* jangka panjang.
2. Jika tetap memakai Redis untuk `pending_review` results, eksplisit konfigurasi persistence (`appendonly yes` + volume mount di docker-compose Task 1.4) dan **tanpa TTL** pada key yang masih berstatus `pending_review` (TTL hanya boleh berlaku setelah `approved`/`rejected` dan sudah diarsipkan).
3. Tambahkan sub-section baru di spec.md §4 yang eksplisit memisahkan "Job Progress Store" (Redis, ephemeral) vs "Audit & Result Archive" (persistent).

---

### 🟠 2.3 Endpoint untuk List Pending Reviews Belum Ada

Spec.md §5 hanya punya `GET /v1/health/correlate/{job_id}` — mengharuskan pemanggil sudah tahu `job_id`. Padahal use case governance-nya adalah: **manajemen/admin perlu melihat daftar semua job yang berstatus `pending_review`** untuk ditinjau, bukan query satu-per-satu by ID yang mereka mungkin tidak tahu.

**Rekomendasi:** Tambahkan endpoint `GET /v1/health/correlate?status=pending_review` (atau `GET /v1/health/correlate/pending`) di spec.md §5 dan Task 5.4 di plan.md.

---

### 🟠 2.4 Definisi "Adapter Virtual" pada Filter MAC Belum Konkret

Spec.md §3.1 menyebut MAC matching *"hanya gunakan adapter dengan `IPEnabled0=1` dan abaikan virtual/VPN adapters"* — namun **kriteria "virtual/VPN" belum didefinisikan secara teknis**. Perlu diketahui bahwa adapter virtual (Hyper-V vEthernet, VMware, VPN client seperti Cisco AnyConnect/TAP) hampir selalu punya `IPEnabled0=1` juga, sehingga filter ini saja tidak cukup untuk mengeksklusi mereka.

**Rekomendasi:** Definisikan kriteria eksplisit di spec.md §3.1, misalnya filter `Description0 NOT LIKE '%Virtual%'`, `NOT LIKE '%VPN%'`, `NOT LIKE '%TAP%'`, `NOT LIKE '%Bluetooth%'` (sesuaikan dengan pola nama adapter yang lazim muncul di `v_GS_NETWORK_ADAPTER` lingkungan AHM — sebaiknya divalidasi dengan sample data riil saat Task 4 dikerjakan, karena pola bisa bervariasi per vendor NIC).

---

### 🟡 2.5 Strategi Pagination: OFFSET/FETCH vs Keyset/Cursor

Spec.md §2 mendefinisikan `get_all_systems(batch_size, offset)` — ini pagination bergaya **limit-offset**. Perlu diketahui bahwa OFFSET besar (mis. offset 50.000 dari total 100.000 baris) relatif berat secara performa di SQL Server karena mesin tetap harus melewati (scan) seluruh baris sebelum offset tersebut untuk setiap batch query.

**Rekomendasi (opsional, nice-to-have):** Jika volume aset SCCM AHM diperkirakan besar (>20.000 record aktif), pertimbangkan keyset pagination (`WHERE ResourceID > :last_seen_id ORDER BY ResourceID`) yang jauh lebih stabil performanya untuk iterasi penuh. Bila volume kecil–menengah, OFFSET/FETCH saat ini sudah cukup — putuskan berdasarkan estimasi jumlah aset riil AHM (masukkan sebagai open question tambahan).

---

### 🟡 2.6 `trustServerCertificate=true` Melemahkan Jaminan TLS

ADR-02 menyatakan koneksi TLS dengan `encrypt=true&trustServerCertificate=true`. Perlu dicatat: `trustServerCertificate=true` berarti **klien tidak memvalidasi certificate chain SQL Server** — koneksi tetap terenkripsi tapi rentan terhadap MITM jika ada pihak di jaringan internal yang bisa menyisipkan diri. Ini sering dipakai sebagai jalan pintas praktis untuk self-signed cert internal, tapi sebaiknya:

**Rekomendasi:**
1. Jadikan `trust_server_certificate` sebagai **config flag terpisah** (bukan hardcoded `true`) di `app/config.py` — tambahkan ke Task 1.2, misalnya `sccm_db_trust_server_cert: bool = True` — agar bisa di-set `False` di production jika AHM ternyata menggunakan CA-signed certificate.
2. Cantumkan pertanyaan ini di daftar "Open Questions": *"Apakah SQL Server SCCM AHM memakai certificate dari internal CA yang trusted, atau self-signed?"*

---

### 🟡 2.7 Scope Boundary: Siapa yang Membangun UI untuk Approve/Reject?

Endpoint `/approve` dan `/reject` sekarang ada di sisi AI Gateway (Python/FastAPI), tapi ketiga dokumen ini scope-nya terbatas pada repo `chatbot-fastapi`. Pertanyaannya: **di mana manajemen/admin AHM sebenarnya mengklik tombol approve** — apakah ada halaman/menu baru di GLPI plugin (PHP) yang memanggil endpoint ini, atau untuk tahap awal cukup dipanggil manual (Postman/API client) oleh tim IT?

Proposal §5.2.5.2 (Plugin business logic) menyiratkan bahwa UI/interaksi pengguna sepenuhnya berada di sisi GLPI plugin, bukan AI Gateway. Jika UI approval perlu dibangun di GLPI plugin, itu **berada di luar scope Task 1–7 di plan.md ini** (yang murni Python), dan perlu dikoordinasikan sebagai task terpisah di repo plugin GLPI, atau minimal dicatat sebagai dependency lintas-repo.

**Rekomendasi:** Tambahkan catatan eksplisit di plan.md/context.md bahwa API `/approve` `/reject` ini **hanya menyediakan backend endpoint**; pembuatan UI tombol approval di GLPI plugin adalah task terpisah (di luar scope repo ini) — supaya ekspektasi stakeholder tidak salah kira bahwa fitur ini "selesai" begitu backend selesai.

---

## 3. Update Daftar Open Questions (Tambahan)

Selain 7 pertanyaan di review sebelumnya (yang sebagian besar sudah terjawab via revisi ini), tambahkan:

8. Bagaimana mekanisme AI Gateway mengetahui identitas user yang melakukan approve/reject — apakah dari header yang dikirim GLPI plugin, atau perlu validasi token tambahan?
9. Apakah audit log dan hasil korelasi `pending_review` perlu disimpan di database persisten terpisah, atau cukup Redis dengan persistence diaktifkan?
10. Estimasi jumlah aset aktif di SCCM AHM (ribuan/puluhan-ribu/ratusan-ribu) — untuk menentukan apakah OFFSET pagination cukup atau perlu keyset pagination?
11. Apakah SQL Server SCCM AHM menggunakan certificate dari CA internal trusted atau self-signed (menentukan apakah `trustServerCertificate` aman di-set `false`)?
12. Siapa yang bertanggung jawab membangun UI approval (tombol approve/reject) — apakah masuk scope proyek ini di sisi GLPI plugin, atau perlu SOW/task terpisah?

---

## 4. Kesimpulan

Revisi ini **jauh lebih matang** dibanding draft awal — seluruh gap governance (human review, audit trail), data quality, dan skalabilitas yang saya soroti sebelumnya sudah diakomodasi secara terstruktur di ADR-08, ADR-09, dan Task 4. Sisa pekerjaan sebelum implementasi terutama bersifat **penajaman detail teknis**, bukan perubahan arsitektur besar:

- **Paling kritis:** kejelasan mekanisme identitas approver (§2.1) dan durability audit log (§2.2) — dua hal ini langsung menentukan apakah tujuan governance/compliance di ADR-08/09 benar-benar tercapai secara substansi, bukan hanya secara struktur kode.
- **Perlu diputuskan sebelum Task 5:** apakah persistent audit store dibutuhkan terpisah dari Redis.
- **Perlu diklarifikasi scope:** siapa membangun UI approval (§2.7), agar tidak ada gap ekspektasi dengan AHM saat delivery.
.