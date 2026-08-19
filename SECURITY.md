# Security Policy

## Supported version

Security fixes are accepted for the current `0.2.x` line. Earlier local release artifacts are retained for research provenance but are not maintained as supported software.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub private vulnerability reporting through the repository Security tab. Include the affected version or commit, impact, reproduction conditions, and the minimum evidence needed to validate the report. Do not include credentials, personal data, classified information, export-controlled material, proprietary operational data, or evidence collected without authorization.

The project is a research simulator, not a deployment assurance product. A valid issue may still affect model integrity, reproducibility, evidence handling, authorization semantics, parser safety, archive safety, or local execution security.

## Response boundary

Receipt of a report does not establish exploitability or operational impact. Reports will be assessed against the affected code path, supported configuration, trust boundary, and reproducible evidence. Confirmed fixes will be separated from scientific result changes. If a correction invalidates a frozen research artifact, the artifact will remain preserved and a new protocol or corrected release will carry the updated result.
