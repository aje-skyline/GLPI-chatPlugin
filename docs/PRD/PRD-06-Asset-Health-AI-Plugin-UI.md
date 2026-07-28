> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-06-Asset-Health-AI-Plugin-UI.md`

---

# PRD-06: Asset Health AI — GLPI Plugin UI

> **Modul:** GLPI Plugin — Health Dashboard & Computer Detail Tab  
> **Sprint:** 7-8  
> **Prioritas:** High  
> **Dependensi:** PRD-02 (Config Page), PRD-05 (Health AI Backend)  
> **PIC Pengembang:** Tim AI  
> **Repo:** `/var/www/glpi/plugins/chatbot/`

---

## 1. Deskripsi Modul

Modul ini mengimplementasikan UI di sisi GLPI Plugin untuk menampilkan data Asset Health AI, mencakup:

1. **Health Dashboard** — Halaman utama dengan overview score, risk distribution, correlation gaps, dan top at-risk assets
2. **Computer Detail Health Tab** — Tab tambahan di halaman detail komputer GLPI yang menampilkan health score dan rekomendasi
3. **Database tables** — Tabel untuk menyimpan health reports dan audit logs
4. **Scheduled job integration** — Cron/scheduled trigger untuk analisis periodik

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Membuat halaman dashboard yang menampilkan ringkasan kesehatan seluruh aset
2. Membuat tab di Computer detail yang menampilkan health score per aset
3. Membuat tabel `glpi_plugin_chatbot_health_reports` untuk menyimpan hasil analisis
4. Membuat tabel `glpi_plugin_chatbot_audit_log` untuk audit trail
5. Mengintegrasikan dengan AI Engine API endpoints

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Dashboard accessible dari menu GLPI (hanya user dengan right `chatbot:dashboard`) | Navigasi test |
| AC-02 | Dashboard menampilkan total aset, risk distribution, warranty summary | Visual check |
| AC-03 | Dashboard menampilkan tabel top at-risk assets dengan health score | Visual check |
| AC-04 | Dashboard menampilkan GLPI-SCCM correlation summary | Visual check |
| AC-05 | "Run Full Analysis" button trigger analysis via AI Engine API | Functional test |
| AC-06 | "Run Correlation" button trigger correlation via AI Engine API | Functional test |
| AC-07 | Health tab muncul di halaman Computer detail | Visual check |
| AC-08 | Health tab menampilkan health score ring, factors, dan recommendations | Visual check |
| AC-09 | Health reports tersimpan di database | DB query check |
| AC-10 | Audit log mencatat setiap analysis trigger | DB query check |
| AC-11 | Dashboard auto-refresh setelah analysis selesai | Functional test |
| AC-12 | Non-admin user tidak bisa akses dashboard | Permission test |

## 3. Spesifikasi Teknis

### 3.1 Database Schema

```sql
-- Ditambahkan di hook.php

CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_health_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT NOT NULL,
    asset_type VARCHAR(50) DEFAULT 'Computer',
    health_score INT,
    risk_category VARCHAR(20),
    report_data JSON,
    sccm_correlation_status VARCHAR(50),
    recommendations JSON,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_asset_id (asset_id),
    INDEX idx_health_score (health_score),
    INDEX idx_risk_category (risk_category),
    INDEX idx_analyzed_at (analyzed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    users_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    session_id VARCHAR(100),
    query_summary TEXT,
    ip_address VARCHAR(45),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_id (users_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.2 File Baru/Dimodifikasi

#### File Baru

| File | Fungsi |
|------|--------|
| `inc/health.class.php` | Class `PluginChatbotHealth` — CRUD health reports |
| `inc/audit.class.php` | Class `PluginChatbotAudit` — Audit logging |
| `front/dashboard.php` | Entry point halaman dashboard |
| `ajax/health.php` | AJAX handler untuk health API calls |
| `views/dashboard.twig` | Twig template untuk dashboard |
| `views/health_tab.twig` | Twig template untuk health tab di Computer detail |
| `js/dashboard.js` | JavaScript untuk dashboard logic |
| `js/health_tab.js` | JavaScript untuk health tab logic |
| `css/dashboard.css` | Styles untuk dashboard |
| `css/health_tab.css` | Styles untuk health tab |

#### File Dimodifikasi

| File | Perubahan |
|------|-----------|
| `hook.php` | Tambah health_reports + audit_log tables, health tab hook |
| `setup.php` | Tambah dashboard menu, rights |
| `inc/chat.class.php` | Update menu structure |

### 3.3 Dashboard Page

#### `front/dashboard.php`

```php
<?php
include('../../../inc/includes.php');
Session::checkLoginUser();

if (!Session::haveRight('chatbot:dashboard', READ)) {
    Html::displayNotFoundError();
}

Html::header(__('Asset Health Dashboard', 'chatbot'), $_SERVER['PHP_SELF'], 'tools', 'PluginChatbotChat');

$apiUrl = PluginChatbotConfig::getConfigValue('api_url', '');
$apiKey = PluginChatbotConfig::getConfigValue('api_key', '');
$healthApiUrl = str_replace('/v1/chat/completions', '', $apiUrl) . '/api/health';
$csrfToken = Session::getNewCSRFToken();

$twig = Twig::load(GLPI_ROOT . '/plugins/chatbot/views', false);
echo $twig->render('dashboard.twig', [
    'health_api_url' => $healthApiUrl,
    'api_key'        => $apiKey,
    'csrf_token'     => $csrfToken,
    'glpi_root'      => GLPI_ROOT,
]);

Html::footer();
```

#### `views/dashboard.twig`

```twig
<div id="health-dashboard" class="ai-dashboard">
    <div class="dashboard-header">
        <h2><i class="fas fa-heartbeat"></i> {{ __('Asset Health Dashboard', 'chatbot') }}</h2>
        <div class="dashboard-actions">
            <button id="btn-analyze-all" class="btn btn-primary" disabled>
                <i class="fas fa-play"></i> {{ __('Run Full Analysis', 'chatbot') }}
            </button>
            <button id="btn-correlate" class="btn btn-secondary" disabled>
                <i class="fas fa-link"></i> {{ __('Run GLPI-SCCM Correlation', 'chatbot') }}
            </button>
            <button id="btn-refresh" class="btn btn-outline-secondary">
                <i class="fas fa-sync-alt"></i> {{ __('Refresh', 'chatbot') }}
            </button>
        </div>
    </div>

    <div id="dashboard-loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin fa-2x"></i>
        <p>{{ __('Loading dashboard data...', 'chatbot') }}</p>
    </div>

    <div id="dashboard-content" class="d-none">
        <div class="dashboard-cards">
            <div class="card card-total">
                <div class="card-icon"><i class="fas fa-desktop"></i></div>
                <div class="card-value" id="total-computers">-</div>
                <div class="card-label">{{ __('Total Assets', 'chatbot') }}</div>
            </div>
            <div class="card card-critical">
                <div class="card-icon"><i class="fas fa-exclamation-triangle"></i></div>
                <div class="card-value" id="critical-count">-</div>
                <div class="card-label">{{ __('Critical', 'chatbot') }}</div>
            </div>
            <div class="card card-high">
                <div class="card-icon"><i class="fas fa-exclamation-circle"></i></div>
                <div class="card-value" id="high-count">-</div>
                <div class="card-label">{{ __('High Risk', 'chatbot') }}</div>
            </div>
            <div class="card card-medium">
                <div class="card-icon"><i class="fas fa-info-circle"></i></div>
                <div class="card-value" id="medium-count">-</div>
                <div class="card-label">{{ __('Medium Risk', 'chatbot') }}</div>
            </div>
            <div class="card card-low">
                <div class="card-icon"><i class="fas fa-check-circle"></i></div>
                <div class="card-value" id="low-count">-</div>
                <div class="card-label">{{ __('Low Risk', 'chatbot') }}</div>
            </div>
        </div>

        <div class="dashboard-sections">
            <div class="section section-status">
                <h3>{{ __('Asset Status Distribution', 'chatbot') }}</h3>
                <div id="status-chart-container">
                    <table class="tab_cadre_fixehov" id="status-table">
                        <thead><tr><th>Status</th><th>Count</th></tr></thead>
                        <tbody id="status-table-body"></tbody>
                    </table>
                </div>
            </div>

            <div class="section section-age">
                <h3>{{ __('Asset Age Distribution', 'chatbot') }}</h3>
                <table class="tab_cadre_fixehov" id="age-table">
                    <thead><tr><th>Age Group</th><th>Count</th></tr></thead>
                    <tbody id="age-table-body"></tbody>
                </table>
            </div>

            <div class="section section-warranty">
                <h3>{{ __('Warranty Summary', 'chatbot') }}</h3>
                <table class="tab_cadre_fixehov" id="warranty-table">
                    <thead><tr><th>Status</th><th>Count</th></tr></thead>
                    <tbody id="warranty-table-body"></tbody>
                </table>
            </div>

            <div class="section section-correlation">
                <h3>{{ __('GLPI ↔ SCCM Correlation', 'chatbot') }}</h3>
                <div id="correlation-content">
                    <p class="text-muted">{{ __('Run correlation to see results', 'chatbot') }}</p>
                </div>
            </div>
        </div>

        <div class="dashboard-table">
            <h3>{{ __('Top At-Risk Assets', 'chatbot') }}</h3>
            <table class="tab_cadre_fixehov">
                <thead>
                    <tr>
                        <th>{{ __('Asset Name', 'chatbot') }}</th>
                        <th>{{ __('Health Score', 'chatbot') }}</th>
                        <th>{{ __('Risk Category', 'chatbot') }}</th>
                        <th>{{ __('Warranty', 'chatbot') }}</th>
                        <th>{{ __('SCCM Status', 'chatbot') }}</th>
                        <th>{{ __('Top Recommendation', 'chatbot') }}</th>
                    </tr>
                </thead>
                <tbody id="risk-table-body">
                    <tr><td colspan="6" class="center">{{ __('No analysis data yet', 'chatbot') }}</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <div id="job-status" class="d-none">
        <div class="alert alert-info">
            <i class="fas fa-spinner fa-spin"></i>
            <span id="job-status-text"></span>
        </div>
    </div>
</div>
```

### 3.4 Health Tab di Computer Detail

#### Hook Registration

```php
// Ditambahkan ke hook.php:

function plugin_chatbot_registerTabs($item) {
    if ($item instanceof Computer) {
        $item->addTab(__('AI Health', 'chatbot'), 'PluginChatbotHealth::showTab');
    }
}

// Di plugin_init_chatbot():
$PLUGIN_HOOKS['item_add']['chatbot'] = ['Computer' => 'plugin_chatbot_registerTabs'];
```

#### `views/health_tab.twig`

```twig
<div class="health-tab" id="health-tab-{{ asset_id }}">
    <div id="health-loading" class="text-center py-3">
        <i class="fas fa-spinner fa-spin"></i> {{ __('Loading health data...', 'chatbot') }}
    </div>

    <div id="health-content" class="d-none">
        <div class="health-score-section">
            <div class="health-score-ring">
                <svg viewBox="0 0 120 120" width="120" height="120">
                    <circle class="ring-bg" cx="60" cy="60" r="54" fill="none" stroke="#e0e0e0" stroke-width="8"/>
                    <circle class="ring-fg" id="score-ring" cx="60" cy="60" r="54" fill="none"
                            stroke-width="8" stroke-linecap="round"
                            stroke-dasharray="0 339.29" transform="rotate(-90 60 60)"/>
                </svg>
                <div class="score-text">
                    <span id="score-value" class="score-number">-</span>
                    <span class="score-label">/100</span>
                </div>
            </div>
            <div class="risk-badge" id="risk-badge">
                <span id="risk-category">-</span>
            </div>
        </div>

        <div class="health-factors-section">
            <h4>{{ __('Health Factors', 'chatbot') }}</h4>
            <table class="tab_cadre_fixehov">
                <thead>
                    <tr>
                        <th>{{ __('Factor', 'chatbot') }}</th>
                        <th>{{ __('Penalty', 'chatbot') }}</th>
                        <th>{{ __('Weight', 'chatbot') }}</th>
                        <th>{{ __('Detail', 'chatbot') }}</th>
                    </tr>
                </thead>
                <tbody id="factors-table-body"></tbody>
            </table>
        </div>

        <div class="health-recommendations-section">
            <h4>{{ __('Recommendations', 'chatbot') }}</h4>
            <ul id="recommendations-list" class="recommendations-list"></ul>
        </div>

        <div class="health-sccm-section" id="sccm-section">
            <h4>{{ __('SCCM Correlation', 'chatbot') }}</h4>
            <div id="sccm-status"></div>
        </div>
    </div>

    <div id="health-error" class="d-none">
        <div class="alert alert-warning">
            {{ __('Health data not available. Run analysis first.', 'chatbot') }}
        </div>
    </div>
</div>
```

### 3.5 JavaScript — dashboard.js

```javascript
const Dashboard = {
    apiUrl: '',
    apiKey: '',

    init(apiUrl, apiKey) {
        this.apiUrl = apiUrl;
        this.apiKey = apiKey;
        this.loadDashboard();
        this.bindEvents();
    },

    async loadDashboard() {
        try {
            const response = await fetch(`${this.apiUrl}/dashboard`, {
                headers: { 'Authorization': `Bearer ${this.apiKey}` }
            });
            const data = await response.json();
            this.renderDashboard(data);
            document.getElementById('dashboard-loading').classList.add('d-none');
            document.getElementById('dashboard-content').classList.remove('d-none');
            document.getElementById('btn-analyze-all').disabled = false;
            document.getElementById('btn-correlate').disabled = false;
        } catch (error) {
            document.getElementById('dashboard-loading').innerHTML =
                `<div class="alert alert-danger">Failed to load dashboard: ${error.message}</div>`;
        }
    },

    renderDashboard(data) {
        document.getElementById('total-computers').textContent = data.total_computers || 0;

        this.renderTable('status-table-body', data.status_distribution, 'status', 'count');
        this.renderTable('age-table-body', data.age_distribution, 'age_group', 'count');

        const warranty = data.warranty_summary || {};
        const warrantyRows = [
            { label: 'Active', value: warranty.active || 0 },
            { label: 'Expiring Soon', value: warranty.expiring_soon || 0 },
            { label: 'Expired', value: warranty.expired || 0 },
            { label: 'No Warranty', value: warranty.no_warranty || 0 },
        ];
        this.renderKeyValueTable('warranty-table-body', warrantyRows);
    },

    renderTable(tbodyId, data, keyCol, valCol) {
        const tbody = document.getElementById(tbodyId);
        tbody.innerHTML = data.map(row =>
            `<tr><td>${row[keyCol] || '-'}</td><td>${row[valCol] || 0}</td></tr>`
        ).join('');
    },

    renderKeyValueTable(tbodyId, rows) {
        const tbody = document.getElementById(tbodyId);
        tbody.innerHTML = rows.map(row =>
            `<tr><td>${row.label}</td><td>${row.value}</td></tr>`
        ).join('');
    },

    async triggerAnalysis() {
        const btn = document.getElementById('btn-analyze-all');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';

        try {
            const response = await fetch(`${this.apiUrl}/analyze`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.apiKey}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ analyze_all: true }),
            });
            const data = await response.json();
            this.pollJobStatus(data.job_id, 'analysis');
        } catch (error) {
            alert('Failed to start analysis: ' + error.message);
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play"></i> Run Full Analysis';
        }
    },

    async triggerCorrelation() {
        const btn = document.getElementById('btn-correlate');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';

        try {
            const response = await fetch(`${this.apiUrl}/correlate`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${this.apiKey}` },
            });
            const data = await response.json();
            this.pollJobStatus(data.job_id, 'correlation');
        } catch (error) {
            alert('Failed to start correlation: ' + error.message);
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-link"></i> Run GLPI-SCCM Correlation';
        }
    },

    async pollJobStatus(jobId, type) {
        const statusDiv = document.getElementById('job-status');
        const statusText = document.getElementById('job-status-text');
        statusDiv.classList.remove('d-none');

        const poll = async () => {
            try {
                const response = await fetch(`${this.apiUrl}/status/${jobId}`);
                const data = await response.json();

                if (data.status === 'PROGRESS') {
                    const progress = data.progress || {};
                    statusText.textContent = `${type}: ${progress.step || 'processing'}... ${progress.progress_pct || ''}%`;
                    setTimeout(poll, 3000);
                } else if (data.status === 'SUCCESS') {
                    statusText.textContent = `${type} completed!`;
                    statusDiv.querySelector('.alert').className = 'alert alert-success';
                    setTimeout(() => {
                        statusDiv.classList.add('d-none');
                        this.loadDashboard();
                    }, 2000);
                    this.resetButtons();
                } else if (data.status === 'FAILURE') {
                    statusText.textContent = `${type} failed: ${data.error}`;
                    statusDiv.querySelector('.alert').className = 'alert alert-danger';
                    this.resetButtons();
                }
            } catch (error) {
                statusText.textContent = `Error polling status: ${error.message}`;
            }
        };
        poll();
    },

    resetButtons() {
        const analyzeBtn = document.getElementById('btn-analyze-all');
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = '<i class="fas fa-play"></i> Run Full Analysis';
        const correlateBtn = document.getElementById('btn-correlate');
        correlateBtn.disabled = false;
        correlateBtn.innerHTML = '<i class="fas fa-link"></i> Run GLPI-SCCM Correlation';
    },

    bindEvents() {
        document.getElementById('btn-analyze-all').addEventListener('click', () => this.triggerAnalysis());
        document.getElementById('btn-correlate').addEventListener('click', () => this.triggerCorrelation());
        document.getElementById('btn-refresh').addEventListener('click', () => this.loadDashboard());
    },
};
```

### 3.6 Audit Class

```php
<?php
// inc/audit.class.php
class PluginChatbotAudit {
    public static function log(string $action, ?string $sessionId = null, ?string $querySummary = null): void {
        global $DB;
        $DB->insert('glpi_plugin_chatbot_audit_log', [
            'users_id'       => Session::getLoginUserID(),
            'action'         => $action,
            'session_id'     => $sessionId,
            'query_summary'  => $querySummary ? substr($querySummary, 0, 500) : null,
            'ip_address'     => $_SERVER['REMOTE_ADDR'] ?? '',
            'created_at'     => date('Y-m-d H:i:s'),
        ]);
    }
}
```

### 3.7 Modifikasi setup.php — Rights & Menu

```php
// Di plugin_init_chatbot(), tambahkan:
$PLUGIN_HOOKS['rights']['chatbot'] = [
    'chatbot:use'       => __('Use Chatbot', 'chatbot'),
    'chatbot:config'    => __('Configure Chatbot', 'chatbot'),
    'chatbot:dashboard' => __('View Health Dashboard', 'chatbot'),
];

// Tambah dashboard ke menu
if (Session::haveRight('chatbot:dashboard', READ)) {
    $PLUGIN_HOOKS['menu_toadd']['chatbot']['dashboard'] = 'PluginChatbotHealth';
}
```

## 4. Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Dashboard Data Flow                           │
│                                                                  │
│  Browser → GET /front/dashboard.php                              │
│         → Twig render dashboard.twig                             │
│         → JS: Dashboard.init()                                   │
│         → JS: fetch /api/health/dashboard                        │
│              → AI Engine: GLPIDBConnector queries                │
│              → AI Engine: return JSON                             │
│         → JS: renderDashboard(data)                              │
│                                                                  │
│  Browser → Click "Run Full Analysis"                             │
│         → JS: fetch /api/health/analyze (POST)                   │
│              → AI Engine: Celery task queued                      │
│              → AI Engine: return job_id                           │
│         → JS: pollJobStatus(job_id)                              │
│              → JS: fetch /api/health/status/{job_id} (GET)       │
│              → AI Engine: return PROGRESS/SUCCESS                 │
│         → JS: on SUCCESS → reloadDashboard()                     │
│                                                                  │
│  Computer Detail → Tab "AI Health"                               │
│         → JS: fetch /api/health/report/{asset_id}                │
│              → AI Engine: HealthScorer.calculate_score()         │
│              → AI Engine: return report JSON                      │
│         → JS: renderHealthTab(data)                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 5. Testing

| ID | Test | Expected |
|----|------|----------|
| T-01 | Akses dashboard sebagai admin | Dashboard ditampilkan |
| T-02 | Akses dashboard sebagai non-admin (no right) | Access denied |
| T-03 | Dashboard load → data ditampilkan | Cards, tables populated |
| T-04 | Click "Run Full Analysis" | Job started, progress shown |
| T-05 | Analysis complete → dashboard refreshes | Updated data |
| T-06 | Click "Run Correlation" | Job started |
| T-07 | Computer detail → "AI Health" tab visible | Tab appears |
| T-08 | Health tab → score ring animated | SVG ring fills |
| T-09 | Health tab → recommendations listed | List populated |
| T-10 | Audit log entry created on analysis trigger | DB row exists |
| T-11 | Dashboard graceful error when AI Engine unreachable | Error message shown |
| T-12 | Health tab graceful error when no data | Warning shown |

## 6. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| PRD-07 (Chat Enhancement) | Audit class | Audit logging untuk chat queries |

## 7. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| AI Engine tidak reachable dari GLPI server | Low | High | Graceful error message, config validation |
| Dashboard load lambat (banyak aset) | Medium | Medium | Pagination, caching, lazy loading |
| Twig rendering issue di GLPI 11 | Low | High | Test di awal sprint, fallback ke inline HTML |
| JSON column tidak support di MariaDB lama | Low | Medium | Check MariaDB version, fallback ke TEXT + JSON encode |

## 8. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Health class | `inc/health.class.php` |
| Audit class | `inc/audit.class.php` |
| Dashboard page | `front/dashboard.php` |
| Health AJAX handler | `ajax/health.php` |
| Dashboard Twig template | `views/dashboard.twig` |
| Health tab Twig template | `views/health_tab.twig` |
| Dashboard JavaScript | `js/dashboard.js` |
| Health tab JavaScript | `js/health_tab.js` |
| Dashboard CSS | `css/dashboard.css` |
| Health tab CSS | `css/health_tab.css` |
| Modified hook.php | `hook.php` |
| Modified setup.php | `setup.php` |
