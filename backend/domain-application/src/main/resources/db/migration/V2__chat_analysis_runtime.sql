ALTER TABLE media_assets DROP CONSTRAINT ck_media_assets_kind;
ALTER TABLE media_assets ADD CONSTRAINT ck_media_assets_kind
    CHECK (kind IN ('original_video', 'original_photo', 'frame', 'annotated_frame'));

CREATE TABLE analysis_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    swing_session_id uuid NOT NULL UNIQUE REFERENCES swing_sessions(id),
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    status varchar(32) NOT NULL,
    media_kind varchar(16) NOT NULL,
    model varchar(64),
    observation_json jsonb,
    reply_json jsonb,
    error_code varchar(64),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT ck_analysis_runs_status
        CHECK (status IN ('running', 'succeeded', 'limited', 'rejected', 'failed', 'deleted')),
    CONSTRAINT ck_analysis_runs_media_kind
        CHECK (media_kind IN ('photo', 'video'))
);
CREATE INDEX ix_analysis_runs_conversation_id ON analysis_runs(conversation_id);
CREATE INDEX ix_analysis_runs_status ON analysis_runs(status);

CREATE TABLE chat_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    analysis_run_id uuid REFERENCES analysis_runs(id),
    role varchar(16) NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_chat_messages_role CHECK (role IN ('user', 'assistant'))
);
CREATE INDEX ix_chat_messages_conversation_id ON chat_messages(conversation_id);
CREATE INDEX ix_chat_messages_created_at ON chat_messages(created_at);

ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

UPDATE storage.buckets
SET allowed_mime_types = ARRAY[
    'video/mp4', 'video/quicktime', 'video/webm',
    'image/jpeg', 'image/png', 'image/webp'
]
WHERE id = 'swing-media';
