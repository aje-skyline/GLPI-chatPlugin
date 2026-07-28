# PRD-02: GLPI Plugin Config Page

> **Modul:** GLPI Plugin — Configuration Page  
> **Sprint:** 1-2  
> **Prioritas:** High  
> **Dependensi:** Tidak ada  
> **PIC Pengembang:** Tim AI  
> **Repo:** `/var/www/glpi/plugins/chatbot/`

---

## 1. Deskripsi Modul

Modul ini mengganti konfigurasi hardcoded di `inc/config.php` (menggunakan `define()`) dengan sistem konfigurasi berbasis database yang bisa dikelola melalui UI di GLPI. Saat ini, setiap perubahan konfigurasi (API URL, API key, model, system prompt) memerlukan edit file PHP langsung di server.

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Membuat tabel `glpi_plugin_chatbot_config` di database GLPI untuk menyimpan konfigurasi
2. Membuat halaman konfigurasi di GLPI yang bisa diakses oleh admin
3. Membuat class `PluginChatbotConfig` untuk CRUD konfigurasi dari database
4. Memodifikasi `ajax/chat.php` dan `front/chat.php` untuk membaca config dari DB
5. Menghapus dependensi pada `inc/config.php` hardcoded constants

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Tabel `glpi_plugin_chatbot_config` terbuat saat plugin install | Cek database setelah install |
| AC-02 | Default config values ter-insert saat install | Query tabel config |
| AC-03 | Halaman config accessible dari menu GLPI (hanya untuk admin) | Navigasi GLPI |
| AC-04 | Admin bisa mengubah API URL, API Key, Model, System Prompt, Max Tokens, Temperature, Streaming | Form submit test |
| AC-05 | Perubahan config langsung berlaku tanpa restart | Ubah config → test chat |
| AC-06 | Chat menggunakan config dari DB, bukan hardcoded | Ubah config → verify di chat response |
| AC-07 | Config page menampilkan current values di form | Visual check |
| AC-08 | CSRF protection aktif di config form | Submit tanpa CSRF token → rejected |
| AC-09 | Hanya user dengan right `config` (UPDATE) yang bisa mengakses halaman config | Test dengan user non-admin |
| AC-10 | Uninstall plugin menghapus tabel config | Cek database setelah uninstall |

## 3. Spesifikasi Teknis

### 3.1 Database Schema

```sql
CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.2 Default Config Values

| config_key | Default Value | Tipe | Deskripsi |
|------------|---------------|------|-----------|
| `api_url` | `http://127.0.0.1:8000/v1/chat/completions` | string | AI Engine API endpoint |
| `api_key` | `internal-glpi-secret-123` | string (sensitive) | API key untuk autentikasi |
| `api_model` | `aj/ai` | string | Model LLM yang digunakan |
| `system_prompt` | *(lihat inc/config.php saat ini)* | text | System prompt untuk AI |
| `max_tokens` | `1024` | integer | Maksimum token respons |
| `temperature` | `0.3` | float | Temperature sampling |
| `streaming_enabled` | `1` | boolean (0/1) | Aktifkan SSE streaming |
| `max_history_messages` | `20` | integer | Maks pesan yang dikirim ke API |
| `max_message_length` | `4000` | integer | Maks karakter per pesan |
| `session_ttl_minutes` | `60` | integer | TTL session chat (menit) |

### 3.3 File yang Dibuat/Dimodifikasi

#### File Baru

| File | Fungsi |
|------|--------|
| `inc/config.class.php` | Class `PluginChatbotConfig` — CRUD config dari DB |
| `front/config.php` | Entry point halaman konfigurasi |
| `ajax/config.php` | AJAX handler untuk save/load config |
| `views/config.twig` | Twig template untuk form konfigurasi |
| `js/config.js` | JavaScript logic untuk config form |
| `css/config.css` | Styles untuk config form |

#### File Dimodifikasi

| File | Perubahan |
|------|-----------|
| `setup.php` | Tambah `config_page` hook |
| `hook.php` | Tambah tabel config di install/uninstall, insert default values |
| `ajax/chat.php` | Ganti `PLUGIN_CHATBOT_API_KEY` dll → baca dari `PluginChatbotConfig` |
| `front/chat.php` | Ganti hardcoded config → baca dari `PluginChatbotConfig` |

### 3.4 Class: PluginChatbotConfig

```php
<?php
class PluginChatbotConfig extends CommonDBTM {
    public static $rightname = 'config';
    public static $table = 'glpi_plugin_chatbot_config';

    public static function getTypeName($nb = 0): string {
        return __('AI Chatbot Configuration', 'chatbot');
    }

    public static function canView(): bool {
        return Session::haveRight('config', READ);
    }

    public static function canCreate(): bool {
        return Session::haveRight('config', UPDATE);
    }

    public static function canUpdate(): bool {
        return Session::haveRight('config', UPDATE);
    }

    public static function getConfigValue(string $key, string $default = ''): string {
        global $DB;
        $result = $DB->request([
            'SELECT' => 'config_value',
            'FROM'   => self::$table,
            'WHERE'  => ['config_key' => $key]
        ])->current();
        return $result ? $result['config_value'] : $default;
    }

    public static function setConfigValue(string $key, string $value): bool {
        global $DB;
        $existing = $DB->request([
            'SELECT' => 'id',
            'FROM'   => self::$table,
            'WHERE'  => ['config_key' => $key]
        ])->current();

        if ($existing) {
            return $DB->update(self::$table, [
                'config_value' => $value,
                'updated_at'   => date('Y-m-d H:i:s'),
            ], ['id' => $existing['id']]);
        } else {
            return $DB->insert(self::$table, [
                'config_key'   => $key,
                'config_value' => $value,
            ]);
        }
    }

    public static function getAllConfig(): array {
        global $DB;
        $config = [];
        foreach ($DB->request(['FROM' => self::$table]) as $row) {
            $config[$row['config_key']] = $row['config_value'];
        }
        return $config;
    }

    public static function setMultipleConfig(array $values): bool {
        global $DB;
        $success = true;
        foreach ($values as $key => $value) {
            if (!self::setConfigValue($key, $value)) {
                $success = false;
            }
        }
        return $success;
    }
}
```

### 3.5 Front Config Page

```php
<?php
// front/config.php
include('../../../inc/includes.php');

Session::checkRight('config', UPDATE);

$plugin = new Plugin();
if (!$plugin->isActivated('chatbot')) {
    Html::displayNotFoundError();
}

if (isset($_POST['save_config'])) {
    $configValues = [
        'api_url'               => $_POST['api_url'] ?? '',
        'api_key'               => $_POST['api_key'] ?? '',
        'api_model'             => $_POST['api_model'] ?? '',
        'system_prompt'         => $_POST['system_prompt'] ?? '',
        'max_tokens'            => $_POST['max_tokens'] ?? '1024',
        'temperature'           => $_POST['temperature'] ?? '0.3',
        'streaming_enabled'     => $_POST['streaming_enabled'] ?? '0',
        'max_history_messages'  => $_POST['max_history_messages'] ?? '20',
        'max_message_length'    => $_POST['max_message_length'] ?? '4000',
        'session_ttl_minutes'   => $_POST['session_ttl_minutes'] ?? '60',
    ];
    PluginChatbotConfig::setMultipleConfig($configValues);
    Session::addMessageAfterRedirect(__('Configuration saved successfully', 'chatbot'));
    Html::back();
}

Html::header(__('AI Chatbot Configuration', 'chatbot'), $_SERVER['PHP_SELF'], 'config', 'PluginChatbotChat');

$config = PluginChatbotConfig::getAllConfig();

$twig = Twig::load(GLPI_ROOT . '/plugins/chatbot/views', false);
echo $twig->render('config.twig', [
    'config'     => $config,
    'csrf_token' => Session::getNewCSRFToken(),
    'form_url'   => Plugin::getWebDir('chatbot') . '/front/config.php',
]);

Html::footer();
```

### 3.6 Twig Template — config.twig

```twig
<div class="chatbot-config-page">
    <form method="post" action="{{ form_url }}" id="chatbot-config-form">
        <input type="hidden" name="_glpi_csrf_token" value="{{ csrf_token }}">

        <div class="card mb-3">
            <div class="card-header">
                <h3><i class="fas fa-plug"></i> {{ __('API Connection', 'chatbot') }}</h3>
            </div>
            <div class="card-body">
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('API URL', 'chatbot') }}</label>
                    <div class="col-sm-9">
                        <input type="url" name="api_url" value="{{ config.api_url|default('') }}"
                               class="form-control" placeholder="http://127.0.0.1:8000/v1/chat/completions">
                        <small class="form-text text-muted">AI Engine chat endpoint URL</small>
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('API Key', 'chatbot') }}</label>
                    <div class="col-sm-9">
                        <div class="input-group">
                            <input type="password" name="api_key" value="{{ config.api_key|default('') }}"
                                   class="form-control" id="api-key-input">
                            <button type="button" class="btn btn-outline-secondary" onclick="toggleApiKey()">
                                <i class="fas fa-eye" id="api-key-icon"></i>
                            </button>
                        </div>
                        <small class="form-text text-muted">Bearer token untuk autentikasi ke AI Engine</small>
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Model', 'chatbot') }}</label>
                    <div class="col-sm-9">
                        <input type="text" name="api_model" value="{{ config.api_model|default('') }}"
                               class="form-control" placeholder="aj/ai">
                    </div>
                </div>
            </div>
        </div>

        <div class="card mb-3">
            <div class="card-header">
                <h3><i class="fas fa-brain"></i> {{ __('AI Behavior', 'chatbot') }}</h3>
            </div>
            <div class="card-body">
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('System Prompt', 'chatbot') }}</label>
                    <div class="col-sm-9">
                        <textarea name="system_prompt" class="form-control" rows="6">{{ config.system_prompt|default('') }}</textarea>
                        <small class="form-text text-muted">Instruksi sistem untuk AI assistant</small>
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Max Tokens', 'chatbot') }}</label>
                    <div class="col-sm-3">
                        <input type="number" name="max_tokens" value="{{ config.max_tokens|default('1024') }}"
                               class="form-control" min="128" max="8192">
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Temperature', 'chatbot') }}</label>
                    <div class="col-sm-3">
                        <input type="number" name="temperature" value="{{ config.temperature|default('0.3') }}"
                               class="form-control" min="0" max="2" step="0.1">
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Streaming', 'chatbot') }}</label>
                    <div class="col-sm-9">
                        <div class="form-check">
                            <input type="checkbox" name="streaming_enabled" value="1"
                                   class="form-check-input" id="streaming-check"
                                   {{ config.streaming_enabled == '1' ? 'checked' : '' }}>
                            <label class="form-check-label" for="streaming-check">
                                {{ __('Enable SSE streaming for real-time responses', 'chatbot') }}
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card mb-3">
            <div class="card-header">
                <h3><i class="fas fa-sliders-h"></i> {{ __('Session Settings', 'chatbot') }}</h3>
            </div>
            <div class="card-body">
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Max History Messages', 'chatbot') }}</label>
                    <div class="col-sm-3">
                        <input type="number" name="max_history_messages" value="{{ config.max_history_messages|default('20') }}"
                               class="form-control" min="2" max="50">
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Max Message Length', 'chatbot') }}</label>
                    <div class="col-sm-3">
                        <input type="number" name="max_message_length" value="{{ config.max_message_length|default('4000') }}"
                               class="form-control" min="100" max="10000">
                    </div>
                </div>
                <div class="form-group row mb-2">
                    <label class="col-sm-3 col-form-label">{{ __('Session TTL (minutes)', 'chatbot') }}</label>
                    <div class="col-sm-3">
                        <input type="number" name="session_ttl_minutes" value="{{ config.session_ttl_minutes|default('60') }}"
                               class="form-control" min="5" max="1440">
                    </div>
                </div>
            </div>
        </div>

        <div class="mb-3">
            <button type="submit" name="save_config" value="1" class="btn btn-primary">
                <i class="fas fa-save"></i> {{ __('Save Configuration', 'chatbot') }}
            </button>
            <button type="button" class="btn btn-secondary" onclick="testConnection()">
                <i class="fas fa-plug"></i> {{ __('Test Connection', 'chatbot') }}
            </button>
        </div>
    </form>

    <div id="test-result" class="alert d-none"></div>
</div>
```

### 3.7 JavaScript — config.js

```javascript
function toggleApiKey() {
    const input = document.getElementById('api-key-input');
    const icon = document.getElementById('api-key-icon');
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('fa-eye', 'fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.replace('fa-eye-slash', 'fa-eye');
    }
}

function testConnection() {
    const form = document.getElementById('chatbot-config-form');
    const formData = new FormData(form);
    const apiUrl = formData.get('api_url');
    const apiKey = formData.get('api_key');
    const resultDiv = document.getElementById('test-result');

    if (!apiUrl) {
        resultDiv.className = 'alert alert-warning';
        resultDiv.textContent = 'API URL tidak boleh kosong';
        resultDiv.classList.remove('d-none');
        return;
    }

    resultDiv.className = 'alert alert-info';
    resultDiv.textContent = 'Testing connection...';
    resultDiv.classList.remove('d-none');

    const healthUrl = apiUrl.replace('/v1/chat/completions', '/health');

    fetch(healthUrl, {
        method: 'GET',
        headers: apiKey ? { 'Authorization': 'Bearer ' + apiKey } : {}
    })
    .then(response => response.json())
    .then(data => {
        resultDiv.className = 'alert alert-success';
        resultDiv.innerHTML = '<strong>Connection successful!</strong><br>' +
            'Service: ' + (data.service || 'N/A') + '<br>' +
            'Version: ' + (data.version || 'N/A') + '<br>' +
            'Model: ' + (data.ai_model || 'N/A');
    })
    .catch(error => {
        resultDiv.className = 'alert alert-danger';
        resultDiv.innerHTML = '<strong>Connection failed!</strong><br>' + error.message;
    });
}
```

### 3.8 Modifikasi hook.php

```php
// Di plugin_chatbot_install(), tambahkan setelah tabel messages:

$DB->query("CREATE TABLE IF NOT EXISTS `glpi_plugin_chatbot_config` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

$defaults = [
    'api_url'              => 'http://127.0.0.1:8000/v1/chat/completions',
    'api_key'              => 'internal-glpi-secret-123',
    'api_model'            => 'aj/ai',
    'system_prompt'        => 'Kamu adalah AI Assistant resmi untuk sistem GLPI (IT Service Management). Bantu pengguna dengan pertanyaan seputar GLPI, tiket, aset IT, dan hal teknis lainnya. Jawab dalam Bahasa Indonesia yang ramah dan profesional. Gunakan emoji secukupnya. Jawab singkat dan jelas. Gunakan format Markdown: **tebal** untuk penekanan, *miring* untuk istilah, `kode` untuk perintah teknis. PENTING: Langsung berikan jawaban akhir tanpa menampilkan proses berpikir, draft, atau catatan internal. Jangan tulis kalimat seperti "Let me think", "I need to", "Check if", atau proses reasoning apapun. Mulai respons langsung dengan jawaban.',
    'max_tokens'           => '1024',
    'temperature'          => '0.3',
    'streaming_enabled'    => '1',
    'max_history_messages' => '20',
    'max_message_length'   => '4000',
    'session_ttl_minutes'  => '60',
];
foreach ($defaults as $key => $value) {
    $DB->insert('glpi_plugin_chatbot_config', [
        'config_key'   => $key,
        'config_value' => $value,
    ]);
}

// Di plugin_chatbot_uninstall(), tambahkan:
$DB->query("DROP TABLE IF EXISTS `glpi_plugin_chatbot_config`");
```

### 3.9 Modifikasi setup.php

```php
// Di plugin_init_chatbot(), tambahkan:
if (Session::haveRight('config', UPDATE)) {
    $PLUGIN_HOOKS['config_page']['chatbot'] = 'front/config.php';
}
```

### 3.10 Modifikasi ajax/chat.php

Ganti semua referensi ke hardcoded constants:

```php
// SEBELUM:
$apiUrl    = PLUGIN_CHATBOT_API_URL;
$apiKey    = PLUGIN_CHATBOT_API_KEY;
$model     = PLUGIN_CHATBOT_API_MODEL;
$prompt    = PLUGIN_CHATBOT_SYSTEM_PROMPT;

// SESUDAH:
$apiUrl    = PluginChatbotConfig::getConfigValue('api_url', 'http://127.0.0.1:8000/v1/chat/completions');
$apiKey    = PluginChatbotConfig::getConfigValue('api_key', 'internal-glpi-secret-123');
$model     = PluginChatbotConfig::getConfigValue('api_model', 'aj/ai');
$prompt    = PluginChatbotConfig::getConfigValue('system_prompt', '');
$maxTokens = (int) PluginChatbotConfig::getConfigValue('max_tokens', '1024');
$temp      = (float) PluginChatbotConfig::getConfigValue('temperature', '0.3');
$streaming = PluginChatbotConfig::getConfigValue('streaming_enabled', '1') === '1';
```

## 4. Data Flow

```
┌──────────────────────────────────────────────────────────┐
│                    Admin User                             │
│                    (config right)                         │
└───────────────────────┬──────────────────────────────────┘
                        │ GET /front/config.php
                        ▼
┌──────────────────────────────────────────────────────────┐
│              Config Page (Twig)                           │
│  - Load current values dari DB                           │
│  - Form: API URL, Key, Model, Prompt, dll               │
│  - Test Connection button                                │
└───────────────────────┬──────────────────────────────────┘
                        │ POST save_config
                        ▼
┌──────────────────────────────────────────────────────────┐
│           PluginChatbotConfig::setMultipleConfig()        │
│  - UPSERT ke glpi_plugin_chatbot_config                  │
└──────────────────────────────────────────────────────────┘
                        │
                        │ Config values sekarang di DB
                        ▼
┌──────────────────────────────────────────────────────────┐
│              ajax/chat.php                                │
│  - Baca config dari DB via PluginChatbotConfig           │
│  - Gunakan values untuk API call                         │
└──────────────────────────────────────────────────────────┘
```

## 5. Keamanan

| Aspek | Implementasi |
|-------|--------------|
| **Access Control** | Hanya user dengan `config` UPDATE right (admin) |
| **CSRF Protection** | `_glpi_csrf_token` di form |
| **API Key Masking** | Input type `password` + toggle show/hide |
| **Input Validation** | Server-side: max length, type check, range check |
| **SQL Injection** | Menggunakan GLPI DB API (parameterized) |

## 6. Testing

| ID | Test | Expected Result |
|----|------|-----------------|
| T-01 | Install plugin → cek tabel config | Tabel terbuat dengan 10 default values |
| T-02 | Akses config page sebagai admin | Form ditampilkan dengan current values |
| T-03 | Akses config page sebagai non-admin | Access denied |
| T-04 | Ubah API URL → save → test chat | Chat menggunakan URL baru |
| T-05 | Ubah streaming ke disabled → test chat | Respons non-streaming |
| T-06 | Test Connection button | Menampilkan status AI Engine |
| T-07 | Submit form tanpa CSRF token | Rejected |
| T-08 | Uninstall plugin → cek tabel config | Tabel terhapus |
| T-09 | Kosongkan API URL → save | Validasi error: field required |
| T-10 | Input temperature > 2 → save | Validasi error: range exceeded |

## 7. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| PRD-06 (Health Plugin UI) | Config page | Health dashboard URL akan ditambahkan ke config |
| PRD-07 (Chat Enhancement) | Config class | Context management settings akan ditambahkan ke config |

## 8. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| Config table tidak terbuat saat upgrade dari v1.0.0 | Medium | High | Tambah migration logic di `hook.php` untuk detect existing install |
| API key terekspos di DB | Low | High | Field masking di UI, pertimbangkan encryption di future sprint |
| Twig tidak tersedia di GLPI 11 | Low | High | GLPI 11 sudah bundle Twig — verifikasi |

## 9. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Config class | `inc/config.class.php` |
| Config page entry | `front/config.php` |
| Config AJAX handler | `ajax/config.php` |
| Config Twig template | `views/config.twig` |
| Config JavaScript | `js/config.js` |
| Config CSS | `css/config.css` |
| Modified hook.php | `hook.php` |
| Modified setup.php | `setup.php` |
| Modified ajax/chat.php | `ajax/chat.php` |
