ALTER TABLE user_context_facts
    ADD COLUMN fact_type varchar(32),
    ADD COLUMN body_region varchar(64),
    ADD COLUMN expires_at timestamptz;

ALTER TABLE user_context_facts
    ADD CONSTRAINT ck_user_context_facts_fact_type
    CHECK (fact_type IS NULL OR fact_type IN (
        'BODY_TRAIT',
        'INJURY',
        'CURRENT_SWING_STYLE',
        'TARGET_SWING_STYLE'
    ));

CREATE INDEX ix_user_context_facts_expiring_injury
    ON user_context_facts(owner_context_id, expires_at)
    WHERE fact_type = 'INJURY' AND expires_at IS NOT NULL;
