CREATE UNIQUE INDEX ux_roadmaps_one_active_per_owner
    ON roadmaps(owner_context_id)
    WHERE is_active = true;
