CREATE TABLE coaching_topics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    conversation_id uuid REFERENCES conversations(id),
    superseded_by_topic_id uuid REFERENCES coaching_topics(id),
    version integer NOT NULL DEFAULT 1,
    status varchar(32) NOT NULL,
    user_problem text NOT NULL,
    root_problem text,
    shot_profile varchar(32) NOT NULL,
    club varchar(64),
    club_group varchar(64),
    short_game_type varchar(64),
    active_hypothesis text,
    current_experiment text,
    carry_forward_feel text,
    evidence_references_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    superseded_at timestamptz,
    CONSTRAINT ck_coaching_topics_version_positive CHECK (version >= 1),
    CONSTRAINT ck_coaching_topics_status
        CHECK (status IN ('ACTIVE', 'PAUSED', 'RESOLVED', 'SUPERSEDED')),
    CONSTRAINT ck_coaching_topics_shot_profile
        CHECK (shot_profile IN ('full_swing', 'short_game')),
    CONSTRAINT ck_coaching_topics_scope_has_club_or_group
        CHECK (club IS NOT NULL OR club_group IS NOT NULL),
    CONSTRAINT ck_coaching_topics_user_problem_not_blank
        CHECK (length(btrim(user_problem)) > 0)
);
CREATE INDEX ix_coaching_topics_owner_context_id ON coaching_topics(owner_context_id);
CREATE INDEX ix_coaching_topics_conversation_id ON coaching_topics(conversation_id);
CREATE INDEX ix_coaching_topics_scope
    ON coaching_topics(owner_context_id, shot_profile, club_group, club, short_game_type);
CREATE UNIQUE INDEX ux_coaching_topics_one_active_per_owner
    ON coaching_topics(owner_context_id)
    WHERE status = 'ACTIVE';

CREATE TABLE roadmaps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    topic_id uuid REFERENCES coaching_topics(id),
    current_milestone_id uuid,
    version integer NOT NULL DEFAULT 1,
    is_active boolean NOT NULL DEFAULT true,
    target_swing text NOT NULL,
    starting_state text,
    next_completion_condition text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT ck_roadmaps_version_positive CHECK (version >= 1),
    CONSTRAINT ck_roadmaps_target_swing_not_blank
        CHECK (length(btrim(target_swing)) > 0)
);
CREATE INDEX ix_roadmaps_owner_context_id ON roadmaps(owner_context_id);
CREATE INDEX ix_roadmaps_topic_id ON roadmaps(topic_id);
CREATE UNIQUE INDEX ux_roadmaps_one_active_per_topic
    ON roadmaps(topic_id)
    WHERE is_active = true AND topic_id IS NOT NULL;

CREATE TABLE roadmap_milestones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    roadmap_id uuid NOT NULL REFERENCES roadmaps(id),
    topic_id uuid REFERENCES coaching_topics(id),
    version integer NOT NULL DEFAULT 1,
    sort_order integer NOT NULL,
    title varchar(200) NOT NULL,
    root_problem text,
    entry_condition text,
    evidence_level varchar(32) NOT NULL DEFAULT 'NOT_STARTED',
    completion_condition text NOT NULL,
    evidence_references_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT ck_roadmap_milestones_version_positive CHECK (version >= 1),
    CONSTRAINT ck_roadmap_milestones_sort_order_positive CHECK (sort_order >= 1),
    CONSTRAINT ck_roadmap_milestones_evidence_level
        CHECK (evidence_level IN (
            'NOT_STARTED',
            'USER_REPORTED_PROGRESS',
            'RESULT_REPEATED',
            'VIDEO_VERIFIED_PROGRESS',
            'MILESTONE_COMPLETED'
        )),
    CONSTRAINT ck_roadmap_milestones_title_not_blank
        CHECK (length(btrim(title)) > 0),
    CONSTRAINT ck_roadmap_milestones_completion_condition_not_blank
        CHECK (length(btrim(completion_condition)) > 0)
);
CREATE INDEX ix_roadmap_milestones_roadmap_id ON roadmap_milestones(roadmap_id);
CREATE INDEX ix_roadmap_milestones_topic_id ON roadmap_milestones(topic_id);
CREATE UNIQUE INDEX ux_roadmap_milestones_roadmap_sort_order
    ON roadmap_milestones(roadmap_id, sort_order);

ALTER TABLE roadmap_milestones ADD CONSTRAINT uq_roadmap_milestones_roadmap_id_id
    UNIQUE (roadmap_id, id);

ALTER TABLE roadmaps ADD CONSTRAINT fk_roadmaps_current_milestone
    FOREIGN KEY (id, current_milestone_id) REFERENCES roadmap_milestones(roadmap_id, id);

CREATE TABLE user_context_facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    superseded_by_fact_id uuid REFERENCES user_context_facts(id),
    version integer NOT NULL DEFAULT 1,
    source_type varchar(32) NOT NULL,
    evidence_level varchar(32) NOT NULL,
    statement text NOT NULL,
    shot_profile varchar(32),
    club varchar(64),
    club_group varchar(64),
    short_game_type varchar(64),
    source_message_id uuid REFERENCES chat_messages(id),
    source_analysis_run_id uuid REFERENCES analysis_runs(id),
    source_episode_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    valid_from timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_user_context_facts_version_positive CHECK (version >= 1),
    CONSTRAINT ck_user_context_facts_source_type
        CHECK (source_type IN ('USER_EXPLICIT', 'VIDEO_OBSERVATION', 'MODEL_HYPOTHESIS')),
    CONSTRAINT ck_user_context_facts_evidence_level
        CHECK (evidence_level IN (
            'USER_REPORTED',
            'RESULT_REPEATED',
            'VIDEO_OBSERVED',
            'REPEATED_OBSERVATION',
            'GLOBAL_CANDIDATE'
        )),
    CONSTRAINT ck_user_context_facts_shot_profile
        CHECK (shot_profile IS NULL OR shot_profile IN ('full_swing', 'short_game')),
    CONSTRAINT ck_user_context_facts_statement_not_blank
        CHECK (length(btrim(statement)) > 0)
);
CREATE INDEX ix_user_context_facts_owner_context_id ON user_context_facts(owner_context_id);
CREATE INDEX ix_user_context_facts_scope
    ON user_context_facts(owner_context_id, shot_profile, club_group, club, short_game_type);
CREATE INDEX ix_user_context_facts_evidence_level ON user_context_facts(evidence_level);

CREATE TABLE progress_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    topic_id uuid NOT NULL REFERENCES coaching_topics(id),
    milestone_id uuid REFERENCES roadmap_milestones(id),
    message_id uuid REFERENCES chat_messages(id),
    analysis_run_id uuid REFERENCES analysis_runs(id),
    version integer NOT NULL DEFAULT 1,
    progress_level varchar(32) NOT NULL,
    user_signal text NOT NULL,
    evidence_references_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    recognized boolean NOT NULL DEFAULT false,
    recognized_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_progress_events_version_positive CHECK (version >= 1),
    CONSTRAINT ck_progress_events_progress_level
        CHECK (progress_level IN (
            'USER_REPORTED_PROGRESS',
            'RESULT_REPEATED',
            'VIDEO_VERIFIED_PROGRESS',
            'MILESTONE_COMPLETED'
        )),
    CONSTRAINT ck_progress_events_user_signal_not_blank
        CHECK (length(btrim(user_signal)) > 0)
);
CREATE INDEX ix_progress_events_owner_context_id ON progress_events(owner_context_id);
CREATE INDEX ix_progress_events_topic_id ON progress_events(topic_id);
CREATE INDEX ix_progress_events_milestone_id ON progress_events(milestone_id);
CREATE INDEX ix_progress_events_unrecognized
    ON progress_events(owner_context_id, topic_id, created_at)
    WHERE recognized = false;

CREATE TABLE recognition_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    topic_id uuid NOT NULL REFERENCES coaching_topics(id),
    progress_event_id uuid NOT NULL REFERENCES progress_events(id),
    roadmap_id uuid REFERENCES roadmaps(id),
    milestone_id uuid REFERENCES roadmap_milestones(id),
    milestone_version integer,
    intensity varchar(32) NOT NULL,
    target varchar(200) NOT NULL,
    recognition_content text NOT NULL,
    evidence_references_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    exposed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_recognition_events_milestone_version_positive
        CHECK (milestone_version IS NULL OR milestone_version >= 1),
    CONSTRAINT ck_recognition_events_intensity
        CHECK (intensity IN (
            'ACKNOWLEDGEMENT',
            'SPECIFIC_RECOGNITION',
            'PROGRESS_DECLARATION',
            'IDENTITY_CONNECTION'
        )),
    CONSTRAINT ck_recognition_events_target_not_blank
        CHECK (length(btrim(target)) > 0),
    CONSTRAINT ck_recognition_events_content_not_blank
        CHECK (length(btrim(recognition_content)) > 0)
);
CREATE UNIQUE INDEX ux_recognition_events_progress_event_id
    ON recognition_events(progress_event_id);
CREATE INDEX ix_recognition_events_owner_context_id ON recognition_events(owner_context_id);
CREATE INDEX ix_recognition_events_topic_exposed_at
    ON recognition_events(topic_id, exposed_at DESC);

CREATE TABLE open_loops (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    topic_id uuid NOT NULL REFERENCES coaching_topics(id),
    version integer NOT NULL DEFAULT 1,
    state varchar(32) NOT NULL,
    carry_forward_feel text,
    next_single_change text NOT NULL,
    next_verification text NOT NULL,
    completion_condition text NOT NULL,
    next_practice_at timestamptz,
    next_upload_expected boolean NOT NULL DEFAULT false,
    predicted_result text,
    question varchar(300),
    fulfilled_by_message_id uuid REFERENCES chat_messages(id),
    fulfilled_by_analysis_run_id uuid REFERENCES analysis_runs(id),
    replaced_by_open_loop_id uuid REFERENCES open_loops(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    CONSTRAINT ck_open_loops_version_positive CHECK (version >= 1),
    CONSTRAINT ck_open_loops_state
        CHECK (state IN ('PENDING', 'FULFILLED', 'REPLACED', 'CANCELLED')),
    CONSTRAINT ck_open_loops_next_single_change_not_blank
        CHECK (length(btrim(next_single_change)) > 0),
    CONSTRAINT ck_open_loops_next_verification_not_blank
        CHECK (length(btrim(next_verification)) > 0),
    CONSTRAINT ck_open_loops_completion_condition_not_blank
        CHECK (length(btrim(completion_condition)) > 0),
    CONSTRAINT ck_open_loops_question_not_blank
        CHECK (question IS NULL OR length(btrim(question)) > 0)
);
CREATE INDEX ix_open_loops_owner_context_id ON open_loops(owner_context_id);
CREATE INDEX ix_open_loops_topic_id ON open_loops(topic_id);
CREATE INDEX ix_open_loops_state ON open_loops(state);
CREATE UNIQUE INDEX ux_open_loops_one_pending_per_topic
    ON open_loops(topic_id)
    WHERE state = 'PENDING';

CREATE TABLE context_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL,
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    conversation_id uuid REFERENCES conversations(id),
    analysis_run_id uuid REFERENCES analysis_runs(id),
    topic_id uuid REFERENCES coaching_topics(id),
    topic_version integer,
    roadmap_id uuid REFERENCES roadmaps(id),
    roadmap_version integer,
    open_loop_id uuid REFERENCES open_loops(id),
    open_loop_version integer,
    context_snapshot_version integer NOT NULL DEFAULT 1,
    message_sequence_start bigint,
    message_sequence_end bigint,
    selected_user_context_fact_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    selected_analysis_episode_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    selected_completed_milestone_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    context_packet_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_context_snapshots_version_positive CHECK (context_snapshot_version >= 1),
    CONSTRAINT ck_context_snapshots_topic_version_positive
        CHECK (topic_version IS NULL OR topic_version >= 1),
    CONSTRAINT ck_context_snapshots_roadmap_version_positive
        CHECK (roadmap_version IS NULL OR roadmap_version >= 1),
    CONSTRAINT ck_context_snapshots_open_loop_version_positive
        CHECK (open_loop_version IS NULL OR open_loop_version >= 1),
    CONSTRAINT ck_context_snapshots_message_sequence_range
        CHECK (
            message_sequence_start IS NULL
            OR message_sequence_end IS NULL
            OR message_sequence_start <= message_sequence_end
        )
);
CREATE UNIQUE INDEX ux_context_snapshots_request_id ON context_snapshots(request_id);
CREATE INDEX ix_context_snapshots_owner_context_id ON context_snapshots(owner_context_id);
CREATE INDEX ix_context_snapshots_conversation_id ON context_snapshots(conversation_id);
CREATE INDEX ix_context_snapshots_analysis_run_id ON context_snapshots(analysis_run_id);

CREATE TABLE coaching_request_applications (
    request_id uuid PRIMARY KEY,
    owner_context_id uuid NOT NULL REFERENCES owner_contexts(id),
    conversation_id uuid REFERENCES conversations(id),
    analysis_run_id uuid REFERENCES analysis_runs(id),
    context_snapshot_id uuid REFERENCES context_snapshots(id),
    applied boolean NOT NULL DEFAULT true,
    blocked_reason varchar(64),
    applied_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_coaching_request_applications_blocked_reason
        CHECK (
            (applied = true AND blocked_reason IS NULL)
            OR (
                applied = false
                AND blocked_reason IS NOT NULL
                AND blocked_reason IN (
                    'DUPLICATE_REQUEST_ID',
                    'VERSION_MISMATCH',
                    'ANALYSIS_FAILED',
                    'CONTRACT_REJECTED'
                )
            )
        )
);
CREATE INDEX ix_coaching_request_applications_owner_context_id
    ON coaching_request_applications(owner_context_id);
CREATE INDEX ix_coaching_request_applications_analysis_run_id
    ON coaching_request_applications(analysis_run_id);
