-- Support tickets: filed from a workspace's Support Desk, answered from the Super Admin Console.
-- Documentation of the schema Hibernate creates (spring.jpa.hibernate.ddl-auto=update); nothing runs this file.

CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id                 UUID PRIMARY KEY,
    workspace_id              UUID NOT NULL REFERENCES workspaces (workspace_id),
    reporter_profile_id       UUID NOT NULL REFERENCES workspace_profiles (profile_id),
    reporter_auth_user_id     UUID NOT NULL,
    subject                   VARCHAR(200) NOT NULL,
    description               TEXT NOT NULL,
    status                    VARCHAR(20) NOT NULL,          -- OPEN | IN_PROGRESS | RESOLVED | CLOSED
    message_count             INTEGER NOT NULL DEFAULT 0,    -- replies; the description is not one
    last_message_at           TIMESTAMP,
    last_message_from_support BOOLEAN NOT NULL DEFAULT FALSE, -- false while the reporter waits for an answer
    created_at                TIMESTAMP NOT NULL,
    updated_at                TIMESTAMP NOT NULL,
    closed_at                 TIMESTAMP,                     -- set on RESOLVED/CLOSED, cleared when reopened
    version                   BIGINT
);

CREATE INDEX IF NOT EXISTS ix_support_tickets_workspace ON support_tickets (workspace_id, created_at);
CREATE INDEX IF NOT EXISTS ix_support_tickets_reporter  ON support_tickets (reporter_profile_id, created_at);
CREATE INDEX IF NOT EXISTS ix_support_tickets_status    ON support_tickets (status, updated_at);

CREATE TABLE IF NOT EXISTS support_ticket_messages (
    message_id          UUID PRIMARY KEY,
    ticket_id           UUID NOT NULL REFERENCES support_tickets (ticket_id),
    author_auth_user_id UUID NOT NULL,
    author_name         VARCHAR(120) NOT NULL,               -- the reporter's display name or "RoleSync Support"
    from_support        BOOLEAN NOT NULL DEFAULT FALSE,
    body                TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_ticket ON support_ticket_messages (ticket_id, created_at);

-- platform_admin_events gains two actions for the audit log:
--   SUPPORT_TICKET_REPLIED, SUPPORT_TICKET_STATUS_CHANGED   (target_type = 'support_ticket')
