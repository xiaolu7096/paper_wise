CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 80),
    password_hash TEXT NOT NULL CHECK (length(password_hash) > 0),
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO users (
    user_id, username, password_hash, role, created_at
) VALUES (
    '00000000-0000-4000-8000-000000000000',
    'local',
    'local-disabled',
    'admin',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX sessions_user_expires ON sessions(user_id, expires_at);

CREATE TABLE user_papers (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, paper_id)
);

INSERT INTO user_papers (user_id, paper_id, created_at)
SELECT '00000000-0000-4000-8000-000000000000', paper_id, created_at
FROM papers;

ALTER TABLE tasks ADD COLUMN user_id TEXT
    REFERENCES users(user_id) DEFAULT '00000000-0000-4000-8000-000000000000';

CREATE INDEX tasks_user_id ON tasks(user_id);

ALTER TABLE messages ADD COLUMN user_id TEXT
    REFERENCES users(user_id) DEFAULT '00000000-0000-4000-8000-000000000000';

CREATE INDEX messages_user_paper_created
ON messages(user_id, paper_id, created_at, message_id);

ALTER TABLE assets ADD COLUMN user_id TEXT
    REFERENCES users(user_id) DEFAULT '00000000-0000-4000-8000-000000000000';

CREATE INDEX assets_user_paper_created ON assets(user_id, paper_id, created_at);

ALTER TABLE annotations ADD COLUMN user_id TEXT
    REFERENCES users(user_id) DEFAULT '00000000-0000-4000-8000-000000000000';

CREATE INDEX annotations_user_paper_page_created
ON annotations(user_id, paper_id, page, created_at, annotation_id);

CREATE TABLE cards_new (
    user_id TEXT NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE
        DEFAULT '00000000-0000-4000-8000-000000000000',
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    content_json TEXT NOT NULL,
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, paper_id)
);

INSERT INTO cards_new (user_id, paper_id, content_json, model, updated_at)
SELECT '00000000-0000-4000-8000-000000000000', paper_id, content_json, model, updated_at
FROM cards;

DROP TABLE cards;

ALTER TABLE cards_new RENAME TO cards;

CREATE TABLE user_model_settings (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'vision')),
    base_url TEXT NOT NULL CHECK (length(base_url) > 0),
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    encrypted_api_key TEXT NOT NULL CHECK (length(encrypted_api_key) > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, kind)
);
