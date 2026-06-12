# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow semantic versioning once the public API
stabilizes.

## Changelog 维护规范

`CHANGELOG.md` 面向使用者、部署者和二次开发者，记录“升级后会感知到什么变化”，而不是复述每个 commit。

推荐写入：

- 新增或移除的用户可见能力、CLI、API、配置项和文档入口。
- 会影响部署、升级、数据迁移、权限、安全边界或运行行为的变化。
- 数据库 schema、Docker 初始化、配置默认值和依赖分组变化。
- 明确的 bug fix，尤其是会影响线上稳定性、数据一致性或兼容性的修复。

不建议写入：

- 单纯测试补充、内部重构、注释调整、README 表述微调。
- 具体函数如何实现、某个内部变量如何传递、某条 commit 的完整摘要。
- 对使用者没有行动价值的实现细节。

`[Unreleased]` 内如果多天连续变更，可以按日期分组；每个日期下仍使用 `Added`、`Changed`、`Fixed`、`Security`、`Docs` 等小节。正式发布时，再把相关条目整理进具体版本号。

## [Unreleased]

本分支自 `d88a45f98053dee7` 以来的主要变更。

### 2026-06-12

#### Added

- 新增 MySQL `chat_messages` 会话记录存储表 `turn_id` 字段，用于精确关联一轮 Q&A。
- 新增 `MYSQL_ENABLED` 配置开关，支持只启用数据库资源、不启用会话存储。
- 新增基础 CLI：`openai-agents-harness doctor` 和 `openai-agents-harness list-capabilities`。
- 新增本地调试 UI 的“删除长期/偏好记忆”按钮，用户可主动清理自己的用户级长期记忆。

#### Changed

- `SESSION_STORE_ENABLED` 现在只控制会话存储，数据库资源由 `MYSQL_ENABLED` 控制；旧配置仅开启 `SESSION_STORE_ENABLED=true` 时仍会隐式启用数据库资源。
- 请求 `options` 统一作为通用 `request_context` 注入 prompt，移除业务特定上下文字段。
- 改进会话消息排序，使用 `turn_id` 关联同一轮 user/assistant 消息，降低同轮消息顺序漂移风险。
- 完善 Python 包元数据和 optional dependency groups，便于 PyPI 发布和按需安装。
- 本地调试 UI 在 `SESSION_STORE_ENABLED=false` 时降级为临时聊天模式，不再把会话列表接口 400 展示为请求失败。

#### Security

- Memory API 增加用户级访问控制：普通用户不能跨用户搜索、列出或清空长期记忆；具备 `memory:admin` scope 的调用方可跨用户操作。

#### Docs

- 补充开源治理文件与协作模板，包括贡献指南、安全策略、行为准则、Issue 模板和 PR 模板。
- 更新 README、配置示例和 Memory 文档，说明 MySQL 资源、会话存储、长期记忆和 Prompt 上下文的推荐用法。
