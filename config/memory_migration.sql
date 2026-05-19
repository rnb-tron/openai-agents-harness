-- Memory System Database Migration
-- 记忆系统数据库表结构

-- 创建记忆记录表
CREATE TABLE IF NOT EXISTS `memory_records` (
  `id` BIGINT NOT NULL COMMENT '主键ID (雪花算法生成)',
  `user_id` VARCHAR(64) NOT NULL COMMENT '用户ID',
  `session_id` VARCHAR(64) NOT NULL COMMENT '会话ID',
  `memory_type` VARCHAR(32) NOT NULL DEFAULT 'long_term' COMMENT '记忆类型: short_term/long_term/episodic/semantic',
  `role` VARCHAR(16) NOT NULL COMMENT '角色: user/assistant/system',
  `content` TEXT NOT NULL COMMENT '记忆内容',
  `embedding_id` VARCHAR(64) DEFAULT NULL COMMENT 'ES向量ID',
  `metadata` JSON DEFAULT NULL COMMENT '扩展元数据 (tokens, timestamp, tags等)',
  `importance_score` FLOAT NOT NULL DEFAULT 0.5 COMMENT '重要性评分 (0-1, 用于遗忘策略)',
  `access_count` INT NOT NULL DEFAULT 0 COMMENT '访问次数',
  `last_accessed_at` DATETIME DEFAULT NULL COMMENT '最后访问时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '软删除标记: 0-正常, 1-已删除',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_user_session_created` (`user_id`, `session_id`, `created_at`),
  KEY `idx_user_memory_type` (`user_id`, `memory_type`),
  KEY `idx_session_created` (`session_id`, `created_at`),
  KEY `idx_importance_score` (`importance_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆记录表';

-- 索引说明:
-- idx_user_id: 按用户查询
-- idx_session_id: 按会话查询
-- idx_user_session_created: 联合索引,优化按用户+会话+时间的查询
-- idx_user_memory_type: 联合索引,优化按用户+记忆类型的查询
-- idx_session_created: 联合索引,优化按会话+时间的查询
-- idx_importance_score: 单列索引,用于遗忘策略排序
