CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE owner_contexts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    anonymous_session_hash text UNIQUE,
    external_provider text,
    external_subject text,
    display_name text,
    default_handedness varchar(16),
    claimed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_owner_contexts_external_subject UNIQUE (external_provider, external_subject)
);

CREATE TABLE conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    active_analysis_run_id uuid,
    shot_profile varchar(32),
    club varchar(64),
    analysis_goal varchar(32),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_conversations_owner_context_id ON conversations(owner_context_id);

CREATE TABLE swing_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    shot_profile varchar(32) NOT NULL,
    club varchar(64) NOT NULL,
    camera_view varchar(32) NOT NULL,
    handedness varchar(16) NOT NULL,
    user_question text,
    user_feel text,
    shot_result_json jsonb,
    comparison_session_id uuid REFERENCES swing_sessions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_swing_sessions_shot_profile
        CHECK (shot_profile IN ('full_swing', 'short_game'))
);
CREATE INDEX ix_swing_sessions_owner_context_id ON swing_sessions(owner_context_id);
CREATE INDEX ix_swing_sessions_conversation_id ON swing_sessions(conversation_id);

CREATE TABLE media_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES swing_sessions(id),
    kind varchar(32) NOT NULL,
    storage_path text NOT NULL UNIQUE,
    sha256 varchar(64),
    duration_ms bigint,
    width integer,
    height integer,
    status varchar(32) NOT NULL DEFAULT 'pending_upload',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_media_assets_kind
        CHECK (kind IN ('original_video', 'frame', 'annotated_frame')),
    CONSTRAINT ck_media_assets_status
        CHECK (status IN ('pending_upload', 'uploaded', 'failed', 'deleted'))
);
CREATE INDEX ix_media_assets_session_id ON media_assets(session_id);
CREATE INDEX ix_media_assets_status ON media_assets(status);

ALTER TABLE owner_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE swing_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'swing-media',
    'swing-media',
    false,
    NULL,
    ARRAY['video/mp4', 'video/quicktime', 'video/webm']
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    allowed_mime_types = EXCLUDED.allowed_mime_types;
