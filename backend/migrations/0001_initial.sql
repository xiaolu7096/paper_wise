CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY
        CHECK (length(paper_id) = 64 AND paper_id NOT GLOB '*[^0-9a-f]*'),
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    title TEXT CHECK (title IS NULL OR length(title) BETWEEN 1 AND 500),
    page_count INTEGER NOT NULL CHECK (page_count >= 1),
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    stage TEXT CHECK (
        stage IS NULL OR stage IN (
            'queued', 'extracting', 'chunking', 'embedding', 'indexing', 'completed'
        )
    ),
    error TEXT CHECK (error IS NULL OR length(error) <= 1000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind = 'ingest'),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    stage TEXT NOT NULL CHECK (
        stage IN ('queued', 'extracting', 'chunking', 'embedding', 'indexing', 'completed')
    ),
    progress INTEGER NOT NULL CHECK (progress BETWEEN 0 AND 100),
    error TEXT CHECK (error IS NULL OR length(error) <= 1000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX tasks_one_active_per_paper
ON tasks(paper_id)
WHERE status IN ('queued', 'running');

CREATE INDEX tasks_paper_id ON tasks(paper_id);

CREATE TABLE chunks (
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    page INTEGER NOT NULL CHECK (page >= 1),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    text TEXT NOT NULL CHECK (length(text) > 0),
    embedding BLOB NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count >= 1),
    PRIMARY KEY (paper_id, chunk_id),
    UNIQUE (paper_id, page, ordinal)
);

CREATE INDEX chunks_paper_page ON chunks(paper_id, page);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    paper_id UNINDEXED,
    chunk_id UNINDEXED,
    search_terms,
    tokenize='unicode61'
);

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL CHECK (length(content) > 0),
    citations_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX messages_paper_created
ON messages(paper_id, created_at, message_id);

CREATE TABLE cards (
    paper_id TEXT PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    content_json TEXT NOT NULL,
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    updated_at TEXT NOT NULL
);

CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    mime_type TEXT NOT NULL CHECK (mime_type IN ('image/png', 'image/jpeg')),
    relative_path TEXT NOT NULL CHECK (length(relative_path) > 0),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    width INTEGER NOT NULL CHECK (width BETWEEN 16 AND 4096),
    height INTEGER NOT NULL CHECK (height BETWEEN 16 AND 4096),
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, asset_id)
);

CREATE INDEX assets_paper_created ON assets(paper_id, created_at);

CREATE TABLE annotations (
    annotation_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'region', 'note')),
    page INTEGER CHECK (page IS NULL OR page >= 1),
    bbox_json TEXT,
    viewport_rotation INTEGER CHECK (
        viewport_rotation IS NULL OR viewport_rotation IN (0, 90, 180, 270)
    ),
    selected_text TEXT CHECK (selected_text IS NULL OR length(selected_text) <= 12000),
    asset_id TEXT,
    ai_explanation TEXT CHECK (ai_explanation IS NULL OR length(ai_explanation) <= 30000),
    note TEXT CHECK (note IS NULL OR length(note) <= 20000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (paper_id, asset_id)
        REFERENCES assets(paper_id, asset_id) ON DELETE RESTRICT,
    CHECK (
        (ai_explanation IS NOT NULL AND length(trim(ai_explanation)) > 0)
        OR (note IS NOT NULL AND length(trim(note)) > 0)
    ),
    CHECK (
        (kind = 'text'
            AND page IS NOT NULL
            AND selected_text IS NOT NULL
            AND length(trim(selected_text)) > 0
            AND bbox_json IS NULL
            AND viewport_rotation IS NULL
            AND asset_id IS NULL)
        OR
        (kind = 'region'
            AND page IS NOT NULL
            AND bbox_json IS NOT NULL
            AND viewport_rotation IS NOT NULL
            AND asset_id IS NOT NULL
            AND selected_text IS NULL)
        OR
        (kind = 'note'
            AND note IS NOT NULL
            AND length(trim(note)) > 0
            AND bbox_json IS NULL
            AND viewport_rotation IS NULL
            AND selected_text IS NULL
            AND asset_id IS NULL
            AND ai_explanation IS NULL)
    )
);

CREATE INDEX annotations_paper_page_created
ON annotations(paper_id, page, created_at, annotation_id);
