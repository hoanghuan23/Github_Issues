-- GitHub Issues crawler schema
-- Mục tiêu:
--   - Theo dõi issue open được tạo trong vòng 24 giờ.
--   - Xếp hạng độ hot theo comments_count.
--   - Chỉ crawl nội dung comment khi sources.include_comments = 1.

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,

    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN ('repo', 'organization', 'keyword', 'label')),

    -- Quy ước identifier:
    -- repo:         microsoft/vscode
    -- organization: kubernetes
    -- keyword:      memory leak
    -- label:        microsoft/vscode:bug
    identifier VARCHAR(300) NOT NULL,
    display_name VARCHAR(300),

    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_accessible BOOLEAN NOT NULL DEFAULT 1,

    -- 1: lấy và lưu nội dung comment; 0: chỉ dùng comments_count từ issue.
    include_comments BOOLEAN NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER,
    schedule_override_minutes INTEGER,

    UNIQUE (source_type, identifier)
);

CREATE INDEX idx_sources_next_scrape
    ON sources (is_active, is_accessible, next_scrape);


CREATE TABLE issues (
    id INTEGER PRIMARY KEY,

    github_issue_id INTEGER NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    repo_full_name VARCHAR(300) NOT NULL,
    issue_number INTEGER NOT NULL,

    title TEXT NOT NULL,
    author_login VARCHAR(100),
    labels_json TEXT,

    state VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (state IN ('open', 'closed')),

    comments_count INTEGER NOT NULL DEFAULT 0,
    html_url TEXT NOT NULL,

    issue_created_at DATETIME NOT NULL,
    issue_updated_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN NOT NULL DEFAULT 1,
    tracking_until DATETIME,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,
    metric_tier VARCHAR(20) NOT NULL DEFAULT 'bootstrap'
        CHECK (metric_tier IN (
            'hot', 'high', 'medium', 'low', 'very_low', 'bootstrap'
        )),

    UNIQUE (github_issue_id),
    UNIQUE (repo_full_name, issue_number)
);

CREATE INDEX idx_issues_open_created
    ON issues (state, issue_created_at);
CREATE INDEX idx_issues_hot
    ON issues (state, comments_count DESC);
CREATE INDEX idx_issues_metric_due
    ON issues (is_tracked, next_metric_update);
CREATE INDEX idx_issues_source
    ON issues (source_id);


-- Một issue có thể được tìm thấy từ nhiều source, ví dụ repo + label + keyword.
CREATE TABLE source_issues (
    source_id INTEGER NOT NULL,
    issue_id INTEGER NOT NULL,

    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source_id, issue_id),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (issue_id)
        REFERENCES issues(id) ON DELETE CASCADE
);

CREATE INDEX idx_source_issues_issue
    ON source_issues (issue_id);


CREATE TABLE analytics_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    cache_date DATE NOT NULL,

    issues_24h INTEGER NOT NULL DEFAULT 0,
    comments_24h INTEGER NOT NULL DEFAULT 0,
    source_score INTEGER NOT NULL DEFAULT 0,
    source_tier INTEGER NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_id, cache_date),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE
);

CREATE INDEX idx_analytics_cache_source_date
    ON analytics_cache (source_id, cache_date);


CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scrape_issues'
        CHECK (job_type IN (
            'scrape_issues',
            'update_metrics',
            'scrape_comments',
            'sync_repos'
        )),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    issues_found INTEGER NOT NULL DEFAULT 0,
    issues_new INTEGER NOT NULL DEFAULT 0,
    comments_found INTEGER NOT NULL DEFAULT 0,
    comments_new INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_jobs_source_time
    ON pipeline_jobs (source_id, started_at);
CREATE INDEX idx_pipeline_jobs_status
    ON pipeline_jobs (status, created_at);


-- Lưu lịch sử comments_count để theo dõi tốc độ tăng thảo luận.
CREATE TABLE issue_metrics (
    id INTEGER PRIMARY KEY,
    issue_id INTEGER NOT NULL,

    comments_count INTEGER NOT NULL DEFAULT 0,
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    FOREIGN KEY (issue_id)
        REFERENCES issues(id) ON DELETE CASCADE
);

CREATE INDEX idx_issue_metrics_issue_time
    ON issue_metrics (issue_id, recorded_at);
CREATE INDEX idx_issue_metrics_recorded_at
    ON issue_metrics (recorded_at);


-- Chỉ ghi bảng này khi source tương ứng có include_comments = 1.
CREATE TABLE issue_comments (
    id INTEGER PRIMARY KEY,
    issue_id INTEGER NOT NULL,

    github_comment_id INTEGER NOT NULL,
    author_login VARCHAR(100),
    comment_body TEXT,
    html_url TEXT,

    comment_created_at DATETIME NOT NULL,
    comment_updated_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (issue_id)
        REFERENCES issues(id) ON DELETE CASCADE,

    UNIQUE (github_comment_id)
);

CREATE INDEX idx_issue_comments_issue_time
    ON issue_comments (issue_id, comment_created_at);


CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,
    error_type VARCHAR(100),
    error_details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_logs_job
    ON pipeline_logs (job_id, created_at);
CREATE INDEX idx_pipeline_logs_source
    ON pipeline_logs (source_id, created_at);
