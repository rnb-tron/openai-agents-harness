# Contributing

Thanks for helping improve OpenAI Agents Harness.

## Development Setup

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install -e ".[dev]"
```

## Local Checks

Run the fast default checks before opening a pull request:

```bash
make format
make test
```

Use integration and e2e suites when changing adapters, storage, or external
provider behavior:

```bash
make test-integration
make test-e2e
```

External model and observability tests must stay opt-in and should not be
required for default local development.

## Contribution Guidelines

- Keep the main runtime path generic. Do not add business-specific tools,
  prompts, routes, or workflow rules to `src/application/orchestration`,
  `src/api`, or `src/capabilities`.
- Prefer explicit dependency injection through `HarnessBuilder`,
  `HarnessContext`, or capability interfaces.
- Keep examples demonstrative. Examples should not become runtime
  dependencies.
- Add focused tests for behavior changes.
- Keep documentation in sync with capability status. Distinguish component
  implementations from features wired into the default `/chat` path.
