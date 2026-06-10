# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow semantic versioning once the public API
stabilizes.

## [Unreleased]

### Added

- MySQL Docker initialization SQL for session store tables with `turn_id`.
- Session store migration guide for existing Docker MySQL volumes.
- Open source contribution, security, and community governance files.

### Changed

- Package metadata now declares project classifiers, keywords, URLs, and
  optional dependency groups.
- Harness default tool registry starts empty; demo tools remain available via
  explicit `ToolRegistry.register_defaults()` calls.
- Request options are exposed as generic `request_context` instead of
  business-specific metadata.
