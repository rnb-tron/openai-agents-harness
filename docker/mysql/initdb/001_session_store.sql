CREATE TABLE IF NOT EXISTS chat_sessions (
  id CHAR(36) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  title VARCHAR(255) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  metadata_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_chat_sessions_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_messages (
  id CHAR(36) NOT NULL,
  session_id CHAR(36) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  content TEXT NOT NULL,
  turn_id VARCHAR(128) NULL,
  model VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'completed',
  metadata_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_chat_messages_user_id (user_id),
  KEY idx_chat_messages_session_created (session_id, created_at),
  KEY idx_chat_messages_session_turn (session_id, turn_id),
  CONSTRAINT fk_chat_messages_session_id
    FOREIGN KEY (session_id)
    REFERENCES chat_sessions (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_session_summaries (
  session_id CHAR(36) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  summary TEXT NOT NULL,
  covered_message_count INT NOT NULL DEFAULT 0,
  model VARCHAR(128) NULL,
  version INT NOT NULL DEFAULT 1,
  metadata_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id),
  KEY ix_chat_session_summaries_user_id (user_id),
  CONSTRAINT fk_chat_session_summaries_session_id
    FOREIGN KEY (session_id)
    REFERENCES chat_sessions (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
