# Security Policy

## Reporting a Vulnerability

Please do not open a public issue for suspected vulnerabilities.

Report security concerns privately to the maintainers with:

- A concise description of the issue.
- Affected versions or commits.
- Reproduction steps or proof of concept, if available.
- Impact assessment and any suggested mitigation.

Until a dedicated security contact is published, use the repository owner's
private reporting channel.

## Security Expectations

- Do not commit real API keys, tokens, passwords, private keys, or production
  environment files.
- Keep `config/*.env` local. Commit only `config/*.env.example`.
- Treat memory, prompt, trace, and tool-call payloads as potentially sensitive.
- New tools that perform external side effects should document risk level and
  approval requirements.
