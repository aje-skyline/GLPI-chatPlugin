# Fixes untuk Session & Context Management Issues

## 🔍 Masalah yang Teridentifikasi

### Gejala yang Dialami:
1. **Nama user selalu "GLPI"** — Bot menjawab nama dari service account, bukan nama user sebenarnya
2. **Pertanyaan berikutnya tidak bisa dijawab** — "Ada berapa asset komputer?" gagal dalam percakapan yang sama
3. **Harus membuat chat baru** — Setiap pertanyaan konteks berbeda memerlukan session baru
4. **Session/Context tidak ter-persist** — `glpi_user_id` hilang antar request

---

## ✅ Perbaikan yang Dilakukan

### **FIX #1: Session ID Resolution (KRITIS)**
**File:** `app/main.py` (fungsi `_resolve_session_id`)

**Masalah:**
- Session ID dibuat berdasarkan hash SELURUH conversation history
- Ketika user mengirim request baru, hash berubah → session ID berbeda
- Akibat: `_user_sessions[old_session_id]` tidak ditemukan, `glpi_user_id` hilang

**Solusi:**
- Ubah ke hash **FIRST USER MESSAGE ONLY** (bukan seluruh history)
- Ini memastikan percakapan yang sama selalu dapat session ID yang sama
- Prioritas: body_sid → X-Session-ID header → fingerprint dari first message

**Keuntungan:**
- Session ID tetap stabil meskipun user mengirim request dengan messages array berbeda
- `glpi_user_id` dapat di-retrieve dari session lama
- Client HARUS tetap mengirim first message untuk stabilitas

---

### **FIX #2: Message History Merge Logic (KRITIS)**
**File:** `app/main.py` (fungsi `_merge_conversation_history`)

**Masalah:**
- Logic merge terlalu ketat, sering fallback ke `incoming_messages` saja
- Server history tidak di-preserve dengan benar
- Akibat: Riwayat percakapan hilang

**Solusi:**
- Perbaiki urutan logika merge:
  1. Jika incoming include full stored history → gunakan incoming (client punya full context)
  2. Jika incoming adalah suffix of stored → gunakan stored
  3. Jika stored[-1] = assistant dan incoming[0] = user → append (normal flow)
  4. Jika ada mismatch → prefer stored (server authoritative)
- Add explicit null checks sebelum indexing

**Keuntungan:**
- History percakapan ter-preserve dengan baik
- Agent mendapat full context untuk menjawab follow-up questions
- Lebih robust terhadap berbagai client behaviors

---

### **FIX #3: User Info Field Priority (CRITICAL)**
**File:** `app/it_glpi_client.py` (fungsi `fetch_user_info`)

**Masalah:**
- `fetch_user_info()` hanya mengembalikan field `name`
- Field `name` sering berisi "GLPI" (service account username)
- Bot menggunakan ini untuk menjawab "Siapa nama saya?" → selalu "GLPI"

**Solusi:**
- Prioritas nama: `realname` > `firstname` > `name` (login/username)
- Ambil yang pertama yang tidak kosong
- Return semua field untuk fleksibilitas tool

**Keuntungan:**
- Bot menjawab dengan nama sebenarnya user (dari realname/firstname)
- Tidak lagi menampilkan service account name "GLPI"

---

### **FIX #4: GetUserInfoTool Display**
**File:** `app/tools.py` (class `GetUserInfoTool`)

**Perubahan:**
- Tool sekarang menggunakan field `name` yang sudah ter-prioritize
- Email ditampilkan hanya jika ada
- Output lebih clean dan meaningful

---

## 📋 Testing Guide

### **Test Case 1: Session Persistence dengan Different Questions**
```
Request 1:
{
  "messages": [{"role": "user", "content": "Nama saya siapa?"}],
  "glpi_user_id": 123
}

Response 1:
- User name ditampilkan (bukan "GLPI")
- X-Session-ID diterima dari header response

Request 2 (dalam percakapan yang sama):
{
  "messages": [
    {"role": "user", "content": "Nama saya siapa?"},
    {"role": "assistant", "content": "[jawaban dari req 1]"},
    {"role": "user", "content": "Ada berapa asset komputer yang terdaftar?"}
  ],
  "X-Session-ID": "[dari response 1]"
}

Expected:
- glpi_user_id HARUS ter-retrieve dari session
- Bot HARUS bisa menjawab question ke-2
- Tidak perlu re-send glpi_user_id
```

### **Test Case 2: Message History Preserved**
```
Request 1: "Siapa supplier kontrak?"
Response 1: [list suppliers]

Request 2: "Berapa nilai kontrak supplier pertama?"
- Agent HARUS punya context tentang supplier dari request 1
- Tidak boleh reply "Saya tidak tahu supplier mana yang Anda maksud"
- History HARUS di-merge dengan benar
```

### **Test Case 3: User Name Display**
```
Request: "Nama saya siapa?"
Expected response:
"Profil User (ID: 123):
• Nama  : [realname atau firstname user, bukan "GLPI"]
• Email : [email user]
• Grup  : [group memberships]"

NOT "GLPI" sebagai nama.
```

### **Test Case 4: New Session with Different Client**
```
Client A: Send X-Session-ID: "aaa"
Client B: Send X-Session-ID: "bbb"

Expected: Dua sessions terpisah, tidak ada cross-contamination.
```

---

## 🚀 Deployment Checklist

- [ ] Rebuild application: `uv pip install -e .` atau restart server
- [ ] Test Case 1: Different questions dalam satu session
- [ ] Test Case 2: Follow-up questions dengan context
- [ ] Test Case 3: User name display (verify bukan "GLPI")
- [ ] Test Case 4: Multi-client isolation
- [ ] Check logs untuk session persistence messages
- [ ] Monitor error logs untuk merge logic issues

---

## 📊 Monitoring

### Important Logs to Check:
```
"Session history empty, using incoming messages only."
→ OK jika hanya di request pertama

"Appending incoming user message to stored assistant history."
→ EXPECTED di request ke-2+

"Restored user_id=%d from session"
→ CRITICAL: Jika tidak ada, session persistence gagal

"History mismatch detected; preferring stored session history"
→ INFO: Server prefer authoritative history
```

### Key Metrics:
- Session ID consistency (should be same for conversation)
- Message history merge success rate
- glpi_user_id persistence across requests
- User name display correctness

---

## 📝 Catatan Penting

### Untuk Client Integration:

1. **MUST: Kirim X-Session-ID header**
   - Capture dari response header pertama
   - Reuse di semua request berikutnya dalam conversation yang sama
   - Format bisa apa saja (UUID, string, dll)

2. **SHOULD: Kirim full conversation history**
   - Include semua messages dari awal conversation
   - Server akan merge dengan stored history
   - Helps dengan recovery jika ada message loss

3. **OPTIONAL: Kirim glpi_user_id hanya di request pertama**
   - Server akan persist ke session
   - Subsequent requests akan auto-retrieve
   - Atau kirim di setiap request untuk extra safety

### Untuk Server/Backend:

1. **Session TTL = 60 menit** (default)
   - Sesuaikan di `.env` jika perlu: `SESSION_TTL_MINUTES=120`
   - Older sessions auto-cleaned

2. **Max session messages = 16**
   - Limit untuk context window LLM
   - Adjust di code jika perlu: `_MAX_SESSION_MESSAGES`

3. **Enable debug logging untuk troubleshoot:**
   - Log level: DEBUG
   - Check `_resolve_session_id` output
   - Check merge history decisions

---

## 🔍 Troubleshooting

### Problem: User name masih "GLPI"
- [ ] Cek di GLPI: apakah realname/firstname diisi?
- [ ] Cek di logs: apa nilai yang di-return dari API?
- [ ] Verify: fetch_user_info() prioritas logic

### Problem: glpi_user_id tidak ter-persist
- [ ] Check X-Session-ID: apakah client mengirim?
- [ ] Check logs: "Resolved session_id from..."
- [ ] Verify: `_user_sessions[session_id]` populated

### Problem: History tidak ter-merge
- [ ] Check logs: apa merge decision?
- [ ] Verify: incoming message format
- [ ] Check: stored vs incoming content matching

### Problem: Agent tidak bisa jawab follow-up
- [ ] Check: message history di request
- [ ] Verify: agent tool dapat context
- [ ] Check: `_MAX_SESSION_MESSAGES` tidak terlalu kecil

---

## 📚 Reference

- Session Management: [main.py](./app/main.py) line 20-87
- User Info: [it_glpi_client.py](./app/it_glpi_client.py) line ~720-760
- Tools: [tools.py](./app/tools.py) line ~420-450
