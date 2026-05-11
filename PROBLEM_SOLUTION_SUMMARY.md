# RINGKASAN MASALAH & SOLUSI

## 🔴 MASALAH UTAMA (Diagnosis)

### Gejala:
1. **Nama user selalu "GLPI"** — Bukan nama sebenarnya dari profile
2. **Pertanyaan berikutnya gagal** — "Ada berapa asset?" tidak bisa dijawab di chat yang sama  
3. **Harus chat baru setiap kali** — Setiap pertanyaan baru perlu session baru
4. **Context hilang** — Bot tidak ingat pertanyaan sebelumnya

### Akar Masalah:

```
┌─────────────────────────────────────────────────────────────────┐
│ MASALAH #1: Session ID Fingerprinting Berubah Setiap Request  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Request 1: "Nama saya siapa?" [glpi_user_id=123]              │
│   ↓                                                             │
│   Hitung session_id = hash(SEMUA messages) = "conv:xxx"       │
│   Simpan: _user_sessions["conv:xxx"] = 123                    │
│                                                                 │
│ Request 2: "Ada berapa aset?" + full history                   │
│   ↓                                                             │
│   HASH BERBEDA! Karena messages beda (ada 3 item, bukan 1)    │
│   Hitung session_id = hash(SEMUA messages) = "conv:yyy"       │
│   Lookup: _user_sessions["conv:yyy"] = NOT FOUND!             │
│   HASIL: glpi_user_id hilang, bot tidak tahu siapa user-nya   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ MASALAH #2: Message History Merge Logic Terlalu Ketat         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Stored History: [User1, Asst1]                                 │
│ Incoming:       [User2]                                         │
│                                                                 │
│ OLD LOGIC:                                                      │
│   ↓ Cek: incoming == stored[:len(incoming)]? NO               │
│   ↓ Cek: stored == incoming? NO                               │
│   ↓ Cek: stored[-1] == "assistant" AND incoming[0] == "user"? │
│   ✓ YES! → Append                                             │
│                                                                 │
│ TAPI: Kalau ada edge case, fallback ke incoming saja!         │
│ HASIL: Stored history hilang → agent kehilangan context       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ MASALAH #3: User Info Menampilkan Service Account Name        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ fetch_user_info(123) di GLPI:                                  │
│   name: "GLPI" ← service account username                      │
│   realname: "Ariel Admin" ← actual real name                   │
│   firstname: "Ariel"                                            │
│                                                                 │
│ Tool mengambil: user_info["name"] = "GLPI"                    │
│ Bot jawab: "Nama Anda adalah GLPI"                            │
│                                                                 │
│ MESTINYA: Prioritas realname/firstname, bukan name field      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ SOLUSI (Implementation)

### FIX #1: Session ID dari FIRST MESSAGE ONLY ⭐

**Before:**
```python
# Hash SELURUH conversation (bisa berubah setiap request)
conversation_key = "|".join(
    msg.get("content", "")[:64]
    for msg in messages
    if msg.get("role") in ("user", "assistant")
)
session_id = f"conv:{hash(conversation_key) & 0xFFFFFFFF}"
```

**After:**
```python
# Hash FIRST USER MESSAGE ONLY (stable untuk conversation yang sama)
for msg in messages:
    if msg.get("role") == "user":
        first_user_message = msg.get("content", "").strip()
        if first_user_message:
            return f"conv:{hash(first_user_message) & 0xFFFFFFFF}"
        break
```

**Hasil:**
- Request 1: "Nama saya siapa?" → session_id = "conv:xxx"
- Request 2: "Nama saya siapa?" + "Ada berapa aset?" → session_id = "conv:xxx" ✓ SAMA!
- glpi_user_id akan ter-retrieve dari session lama

---

### FIX #2: Robust Message History Merge Logic ⭐

**Before:**
```python
# Fallback ke incoming saja kalau ada mismatch
if [kondisi kompleks]:
    # append
else:
    return incoming_messages  # ← Stored history HILANG!
```

**After:**
```python
# Urutan prioritas:
1. Jika incoming include full stored history → gunakan incoming (client punya full context)
2. Jika incoming adalah suffix of stored → gunakan stored
3. Jika stored[-1]="asst" dan incoming[0]="user" → APPEND (normal flow)
4. Jika ada mismatch → PREFER STORED (server authoritative) ← PENTING!

# Tidak ada lagi fallback yang menghilangkan history
```

**Hasil:**
- History percakapan ter-preserve di semua case
- Agent mendapat full context untuk follow-up questions
- Bot bisa jawab "Ada berapa aset?" setelah "Siapa saya?"

---

### FIX #3: User Name Priority ⭐

**Before:**
```python
return {
    "name": data.get("name", ""),  # ← "GLPI" (service account!)
    ...
}
```

**After:**
```python
display_name = (
    data.get("realname", "").strip() or     # Try realname first
    data.get("firstname", "").strip() or    # Then firstname
    data.get("name", "")                    # Finally name (login)
)
return {
    "name": display_name,  # ← "Ariel Admin" atau "Ariel"
    ...
}
```

**Hasil:**
- Bot menjawab "Nama Anda adalah Ariel Admin" (bukan GLPI)
- Sesuai dengan profile yang di-set user

---

## 📊 Perbandingan Sebelum vs Sesudah

| Masalah | Sebelum | Sesudah |
|---------|---------|---------|
| **Session ID** | Berubah setiap request | Stable selama conversation |
| **glpi_user_id** | Hilang di request ke-2 | Ter-retrieve dengan baik |
| **Message History** | Sering hilang | Di-preserve selalu |
| **Follow-up Questions** | Gagal (no context) | Berhasil (full context) |
| **User Name** | "GLPI" (service account) | "Ariel Admin" (real name) |
| **Multi-turn Conversation** | Perlu chat baru | Dalam 1 chat saja |

---

## 🚀 QUICK START: Testing Fixes

### 1. Verify No Syntax Errors:
```bash
cd /home/ariel/projects/chatbot-fastapi
python -m py_compile app/main.py app/tools.py app/it_glpi_client.py
# Output: No error = syntax OK ✓
```

### 2. Test Session Persistence:
```bash
# Request 1
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Nama saya siapa?"}],
    "glpi_user_id": 123
  }'

# Capture X-Session-ID dari response

# Request 2 - GUNAKAN SESSION ID YANG SAMA
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "X-Session-ID: [dari response 1]" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Nama saya siapa?"},
      {"role": "assistant", "content": "[jawaban dari req 1]"},
      {"role": "user", "content": "Ada berapa asset komputer?"}
    ]
  }'

# Expected: Bot bisa jawab question ke-2 dengan correct glpi_user_id
```

### 3. Test User Name Display:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Siapa nama saya?"}],
    "glpi_user_id": 123
  }'

# Expected: "Nama Anda adalah [realname/firstname]"
# NOT: "Nama Anda adalah GLPI"
```

### 4. Check Logs:
```bash
# See session resolution
grep "Resolved session_id" /path/to/logs

# See history merge decision
grep "Appending incoming user message" /path/to/logs
grep "History mismatch" /path/to/logs

# See user_id persistence
grep "Stored user_id" /path/to/logs
grep "Restored user_id" /path/to/logs
```

---

## 📋 Deployment Steps

1. **Backup current version:**
   ```bash
   git commit -am "Pre-fix backup"
   ```

2. **Apply changes:**
   - Changes sudah di-apply ke 3 files:
     - `app/main.py` (session ID + merge logic)
     - `app/it_glpi_client.py` (user info priority)
     - `app/tools.py` (display)

3. **Rebuild:**
   ```bash
   cd /home/ariel/projects/chatbot-fastapi
   source .venv/bin/activate
   uv pip install -e .
   ```

4. **Restart server:**
   ```bash
   # If using uvicorn
   pkill -f "uvicorn.*main:app"
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. **Verify:**
   - Run test cases di atas
   - Check logs untuk "Appending incoming" messages
   - Verify user names display correctly

---

## 🔍 Troubleshooting

| Gejala | Diagnosis | Solusi |
|--------|-----------|--------|
| "Nama masih GLPI" | Field realname kosong di GLPI | Isi realname/firstname di GLPI User profile |
| "glpi_user_id hilang" | X-Session-ID tidak di-send | Client HARUS send X-Session-ID header dari response sebelumnya |
| "History masih hilang" | Merge logic tidak jalan | Check logs: grep "Appending" |
| "Bot tidak jawab Q2" | Context tidak ter-pass | Verify: Request 2 include full messages array |

---

## 📚 File Changes Summary

```
app/main.py
  ✓ _resolve_session_id() → Use first message hash only
  ✓ _merge_conversation_history() → Robust merge logic, prefer stored
  ✓ chat_completions() → Pass body_sid to resolver

app/it_glpi_client.py
  ✓ fetch_user_info() → Prioritize realname > firstname > name

app/tools.py
  ✓ GetUserInfoTool._run() → Display prioritized name field

Documentation Added:
  ✓ FIXES_AND_TESTING.md → Detailed testing guide
  ✓ test_session_fixes.py → Automated test suite
```

---

**Status:** ✅ **ALL FIXES APPLIED & NO SYNTAX ERRORS**

Semua 3 masalah utama sudah diperbaiki. Sistem siap untuk testing & deployment.
