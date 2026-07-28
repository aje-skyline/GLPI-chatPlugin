> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-07-Chat-Enhancement-Plugin.md`

---

# PRD-07: Chat Enhancement — Plugin Refactor

> **Modul:** GLPI Plugin — UI Refactor ke Twig, Access Control, Audit Logging, Context Management  
> **Sprint:** 9-10  
> **Prioritas:** Medium  
> **Dependensi:** PRD-02 (Config Page), PRD-06 (Health Plugin UI)  
> **PIC Pengembang:** Tim AI  
> **Repo:** `/var/www/glpi/plugins/chatbot/`

---

## 1. Deskripsi Modul

Modul ini melakukan refactor dan enhancement pada GLPI Plugin yang sudah ada, mencakup:

1. **Twig Refactor** — Memindahkan inline HTML dari `front/chat.php` ke Twig templates
2. **Access Control Enhancement** — Menambahkan profile-based permissions (bukan hanya login check)
3. **Audit Logging** — Mencatat semua aktivitas chat dan config changes
4. **Context Management** — Mengaktifkan user context (computers, tickets) yang saat ini di-comment out

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Memisahkan logic (PHP) dari presentation (Twig) sesuai konvensi GLPI 11
2. Mengganti permission check sederhana (`getLoginUserID`) dengan profile-based rights
3. Mencatat setiap chat query, config change, dan health analysis di audit log
4. Mengirimkan konteks pengguna (komputer, tiket aktif) ke AI Engine untuk respons yang lebih relevan

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Chat UI dirender dari Twig template, bukan inline HTML | Code review |
| AC-02 | CSS dan JS diload sebagai proper assets, bukan via `file_get_contents()` | Network tab check |
| AC-03 | User tanpa right `chatbot:use` tidak bisa akses chat | Permission test |
| AC-04 | User tanpa right `chatbot:config` tidak bisa akses config page | Permission test |
| AC-05 | User tanpa right `chatbot:dashboard` tidak bisa akses dashboard | Permission test |
| AC-06 | Setiap chat query dicatat di `glpi_plugin_chatbot_audit_log` | DB query check |
| AC-07 | Setiap config change dicatat di audit log | DB query check |
| AC-08 | User context (computers, tickets) dikirim ke AI Engine | API request check |
| AC-09 | Chat berfungsi sama seperti sebelum refactor | Functional regression test |
| AC-10 | SSE streaming berfungsi setelah refactor | Browser test |
| AC-11 | Session management (create, rename, delete) berfungsi | Functional test |
| AC-12 | Fallback ke inline HTML jika Twig tidak tersedia | Test dengan Twig disabled |

## 3. Spesifikasi Teknis

### 3.1 Twig Refactor

#### File Baru

| File | Fungsi |
|------|--------|
| `views/chat.twig` | Chat UI template (extract dari `front/chat.php`) |

#### `front/chat.php` — Refactored

```php
<?php
include('../../../inc/includes.php');
Session::checkLoginUser();

if (!Session::haveRight('chatbot:use', READ)) {
    Html::displayNotFoundError();
}

$plugin = new Plugin();
if (!$plugin->isActivated('chatbot')) {
    Html::displayNotFoundError();
}

Html::header(__('AI Chatbot', 'chatbot'), $_SERVER['PHP_SELF'], 'tools', 'PluginChatbotChat');

$config = PluginChatbotConfig::getAllConfig();
$userName = Session::getLoginUserName();
$csrfToken = Session::getNewCSRFToken();
$ajaxUrl = Plugin::getWebDir('chatbot') . '/ajax';
$glpiUserId = Session::getLoginUserID();
$pluginDir = Plugin::getWebDir('chatbot');

$twig = Twig::load(GLPI_ROOT . '/plugins/chatbot/views', false);
echo $twig->render('chat.twig', [
    'config'       => $config,
    'user_name'    => $userName,
    'csrf_token'   => $csrfToken,
    'ajax_url'     => $ajaxUrl,
    'glpi_user_id' => $glpiUserId,
    'plugin_dir'   => $pluginDir,
    'model_name'   => $config['api_model'] ?? 'AI',
]);

Html::footer();
```

#### `views/chat.twig` — Extract dari inline HTML

Template ini berisi seluruh HTML yang saat ini inline di `front/chat.php`, dengan variabel PHP diganti Twig variables:

```twig
{# Key replacements dari inline HTML ke Twig: #}
{# PHP: $userName → Twig: user_name #}
{# PHP: $CSRF_TOKEN → Twig: csrf_token #}
{# PHP: $AJAX_URL → Twig: ajax_url #}
{# PHP: $GLPI_USER_ID → Twig: glpi_user_id #}
{# PHP: file_get_contents(css) → Twig: <link href="{{ plugin_dir }}/css/chat.css"> #}
{# PHP: file_get_contents(js) → Twig: <script src="{{ plugin_dir }}/js/chat.js"> #}

<div id="hw-wrap">
    <div class="hw-header">
        <div class="hw-header-left">
            <i class="fas fa-robot"></i>
            <span class="hw-title">AI Chatbot</span>
            <span class="hw-model-badge">{{ model_name }}</span>
            <span class="hw-online-indicator"></span>
        </div>
        <button id="hw-sidebar-toggle" class="hw-btn-icon">
            <i class="fas fa-bars"></i>
        </button>
    </div>

    <div class="hw-messages" id="hw-messages">
        <div class="hw-welcome">
            <div class="hw-welcome-icon">🤖</div>
            <h3>Halo, {{ user_name }}!</h3>
            <p>Saya adalah AI Assistant untuk GLPI. Ada yang bisa saya bantu?</p>
            <div class="hw-suggestions">
                <button class="hw-suggestion" onclick="useSuggestion('Daftar komputer saya')">
                    💻 Komputer saya
                </button>
                <button class="hw-suggestion" onclick="useSuggestion('Tiket aktif saya')">
                    🎫 Tiket aktif
                </button>
                <button class="hw-suggestion" onclick="useSuggestion('Berapa total komputer?')">
                    📊 Total aset
                </button>
                <button class="hw-suggestion" onclick="useSuggestion('Kesehatan aset saya')">
                    ❤️ Kesehatan aset
                </button>
            </div>
        </div>
    </div>

    <div class="hw-typing" id="hw-typing" style="display:none">
        <span class="hw-dot"></span>
        <span class="hw-dot"></span>
        <span class="hw-dot"></span>
    </div>

    <div class="hw-input-bar">
        <button id="hw-clear" class="hw-btn-icon" title="Clear chat">
            <i class="fas fa-trash-alt"></i>
        </button>
        <textarea id="hw-input" placeholder="Ketik pesan..." rows="1"></textarea>
        <button id="hw-send" class="hw-btn-send">
            <i class="fas fa-paper-plane"></i>
        </button>
    </div>
</div>

<link rel="stylesheet" href="{{ plugin_dir }}/css/chat.css">
<script>
    const GLPI_USER_ID = {{ glpi_user_id }};
    const AJAX_URL = "{{ ajax_url }}";
    const userName = "{{ user_name }}";
    const CSRF_TOKEN = "{{ csrf_token }}";
</script>
<script src="{{ plugin_dir }}/js/chat.js"></script>
```

### 3.2 Access Control Enhancement

#### Rights Registration

```php
// Modifikasi setup.php — plugin_init_chatbot():

// Register rights
$PLUGIN_HOOKS['rights']['chatbot'] = [
    'chatbot:use'       => __('Use Chatbot', 'chatbot'),
    'chatbot:config'    => __('Configure Chatbot', 'chatbot'),
    'chatbot:dashboard' => __('View Health Dashboard', 'chatbot'),
];

// Menu hanya untuk user yang punya right
if (Session::haveRight('chatbot:use', READ)) {
    $PLUGIN_HOOKS['menu_toadd']['chatbot'] = [
        'tools' => 'PluginChatbotChat',
    ];
}

if (Session::haveRight('chatbot:config', UPDATE)) {
    $PLUGIN_HOOKS['config_page']['chatbot'] = 'front/config.php';
}
```

#### Class Permission Updates

```php
// Modifikasi inc/chat.class.php:

public static function canView(): bool {
    return Session::haveRight('chatbot:use', READ);
}

public static function canCreate(): bool {
    return false;
}

// Tambahkan:
public static function canUseChat(): bool {
    return Session::haveRight('chatbot:use', READ);
}

public static function canViewDashboard(): bool {
    return Session::haveRight('chatbot:dashboard', READ);
}

public static function canConfig(): bool {
    return Session::haveRight('chatbot:config', UPDATE);
}
```

#### AJAX Endpoint Protection

```php
// Modifikasi ajax/chat.php — tambahkan di awal:
if (!Session::haveRight('chatbot:use', READ)) {
    http_response_code(403);
    echo json_encode(['error' => 'Access denied']);
    exit;
}

// Modifikasi ajax/sessions.php — tambahkan di awal:
if (!Session::haveRight('chatbot:use', READ)) {
    http_response_code(403);
    echo json_encode(['error' => 'Access denied']);
    exit;
}
```

### 3.3 Audit Logging

#### Integration Points

```php
// Di ajax/chat.php — setelah user message disimpan:
PluginChatbotAudit::log('chat_query', $sessionId, $userMessage);

// Di ajax/chat.php — setelah assistant response disimpan:
PluginChatbotAudit::log('chat_response', $sessionId, null);

// Di front/config.php — setelah config save:
PluginChatbotAudit::log('config_change', null, json_encode($configValues));

// Di ajax/health.php — setelah trigger analysis:
PluginChatbotAudit::log('health_analysis', null, 'analyze_all');

// Di ajax/sessions.php — setiap create/rename/delete:
PluginChatbotAudit::log('session_create', $sessionId, null);
PluginChatbotAudit::log('session_rename', $sessionId, $newTitle);
PluginChatbotAudit::log('session_delete', $sessionId, null);
```

### 3.4 Context Management

#### Enable User Context

```php
// Modifikasi ajax/chat.php — aktifkan user context yang di-comment out:

function plugin_chatbot_get_user_context($usersId) {
    global $DB;

    $context = [];

    // User name
    $user = $DB->request([
        'SELECT' => ['name', 'realname', 'firstname'],
        'FROM'   => 'glpi_users',
        'WHERE'  => ['id' => $usersId]
    ])->current();
    if ($user) {
        $context['user_name'] = trim(($user['firstname'] ?? '') . ' ' . ($user['realname'] ?? '')) ?: $user['name'];
    }

    // User's computers (limit 10)
    $computers = $DB->request([
        'SELECT' => ['id', 'name', 'serial'],
        'FROM'   => 'glpi_computers',
        'WHERE'  => ['users_id' => $usersId, 'is_deleted' => 0],
        'LIMIT'  => 10,
    ]);
    $compList = [];
    foreach ($computers as $c) {
        $compList[] = $c['name'] . ' (S/N: ' . $c['serial'] . ')';
    }
    if ($compList) {
        $context['computers'] = implode(', ', $compList);
    }

    // Active tickets (limit 5)
    $tickets = $DB->request([
        'SELECT' => ['id', 'name', 'status'],
        'FROM'   => 'glpi_tickets',
        'WHERE'  => [
            'users_id_recipient' => $usersId,
            'status' => [
                CommonITILObject::INCOMING,
                CommonITILObject::ASSIGNED,
                CommonITILObject::PLANNED,
                CommonITILObject::WAITING,
            ],
        ],
        'LIMIT'  => 5,
        'ORDER'  => 'date DESC',
    ]);
    $ticketList = [];
    foreach ($tickets as $t) {
        $ticketList[] = '#' . $t['id'] . ' ' . $t['name'];
    }
    if ($ticketList) {
        $context['active_tickets'] = implode(', ', $ticketList);
    }

    return $context;
}

// Build context string untuk system prompt:
$contextData = plugin_chatbot_get_user_context($usersId);
$contextStr = "Data pengguna saat ini:\n";
if (!empty($contextData['user_name'])) {
    $contextStr .= "- Nama: {$contextData['user_name']}\n";
}
if (!empty($contextData['computers'])) {
    $contextStr .= "- Komputer: {$contextData['computers']}\n";
}
if (!empty($contextData['active_tickets'])) {
    $contextStr .= "- Tiket aktif: {$contextData['active_tickets']}\n";
}

// Tambahkan ke system prompt:
$systemPrompt = $prompt . "\n\n" . $contextStr;
```

## 4. Testing

| ID | Test | Expected |
|----|------|----------|
| T-01 | Chat UI dirender dari Twig | HTML structure sama, CSS/JS loaded as assets |
| T-02 | User dengan right `chatbot:use` bisa akses chat | Chat page accessible |
| T-03 | User tanpa right `chatbot:use` tidak bisa akses chat | 403 Forbidden |
| T-04 | User dengan right `chatbot:config` bisa akses config | Config page accessible |
| T-05 | User tanpa right `chatbot:config` tidak bisa akses config | Access denied |
| T-06 | Chat query → audit log entry created | DB row with action='chat_query' |
| T-07 | Config change → audit log entry created | DB row with action='config_change' |
| T-08 | Session create → audit log entry created | DB row with action='session_create' |
| T-09 | User context (computers, tickets) muncul di system prompt | API request inspection |
| T-10 | Chat berfungsi normal setelah refactor | Send message → get response |
| T-11 | SSE streaming berfungsi | Real-time token streaming |
| T-12 | Session CRUD berfungsi | Create, rename, delete sessions |

## 5. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| Twig template rendering berbeda dari inline HTML | Medium | Medium | Pixel-perfect comparison test |
| Rights system tidak kompatibel dengan GLPI 11 | Low | High | Test di GLPI 11 instance, refer GLPI docs |
| User context terlalu panjang → token limit | Medium | Low | Truncate context, limit items |
| Audit log table membesar cepat | Medium | Low | Retention policy, periodic cleanup |

## 6. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Chat Twig template | `views/chat.twig` |
| Refactored front/chat.php | `front/chat.php` |
| Modified setup.php (rights) | `setup.php` |
| Modified inc/chat.class.php | `inc/chat.class.php` |
| Modified ajax/chat.php (context + audit) | `ajax/chat.php` |
| Modified ajax/sessions.php (audit) | `ajax/sessions.php` |
