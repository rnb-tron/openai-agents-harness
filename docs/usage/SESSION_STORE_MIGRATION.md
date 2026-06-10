# Session Store Migration

This guide covers local Docker MySQL schema changes for the session store.

## Fresh Docker MySQL

`docker-compose.storage.yml` mounts `docker/mysql/initdb/` into the official MySQL
`/docker-entrypoint-initdb.d/` directory. When the `agent_mysql_data` volume is
empty, MySQL runs `001_session_store.sql` automatically and creates:

- `chat_sessions`
- `chat_messages`, including `turn_id`
- `chat_session_summaries`

## Existing Docker MySQL

MySQL only runs init scripts on first initialization. If you already created the
`agent_mysql_data` volume before `turn_id` was added, apply this migration:

```sql
ALTER TABLE chat_messages
  ADD COLUMN turn_id VARCHAR(128) NULL AFTER content;

CREATE INDEX idx_chat_messages_session_turn
  ON chat_messages (session_id, turn_id);
```

Check whether the migration is already applied:

```sql
SHOW COLUMNS FROM chat_messages LIKE 'turn_id';
SHOW INDEX FROM chat_messages WHERE Key_name = 'idx_chat_messages_session_turn';
```

## Backfill Legacy Rows

Old rows can keep `turn_id = NULL` without breaking new chats. New requests
generate a `turn_id` and persist it.

If you want historical user and assistant messages grouped into turns, backfill
by natural conversation order:

```sql
WITH ordered AS (
  SELECT
    id,
    session_id,
    role,
    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)
      OVER (
        PARTITION BY session_id
        ORDER BY created_at ASC,
                 CASE
                   WHEN role = 'user' THEN 0
                   WHEN role = 'assistant' THEN 1
                   ELSE 2
                 END,
                 id ASC
      ) AS turn_no
  FROM chat_messages
  WHERE turn_id IS NULL
),
mapped AS (
  SELECT
    id,
    CONCAT('legacy_', session_id, '_', turn_no) AS new_turn_id
  FROM ordered
  WHERE turn_no > 0
)
UPDATE chat_messages m
JOIN mapped x ON m.id = x.id
SET m.turn_id = x.new_turn_id
WHERE m.turn_id IS NULL;
```

Backfill is best-effort if old rows have identical `created_at` values and no
other stable ordering field.
