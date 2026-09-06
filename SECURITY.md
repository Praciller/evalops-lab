# Security Policy

## Supported versions

Security fixes are scoped to the latest `main` and the latest published milestone release.

## Reporting a vulnerability

Do not use a public GitHub issue for an undisclosed vulnerability. Private Vulnerability Reporting is enabled for this repository; use GitHub's **Report a vulnerability** flow on the repository Security/Advisories surface to submit a private report to the maintainer.

Please avoid including secrets or private evidence in any report that is not private.

## Sensitive surfaces

Please treat the following as security-sensitive:

- leaked secrets, API credentials, or tokens;
- exposure of private evidence artifacts, raw datasets, prompts, responses, or hidden reasoning;
- bypasses of the strict public-evidence sanitization boundary;
- path traversal or unintended publication of local files/artifacts;
- dependency, workflow, or other software supply-chain compromise.

Reports should include the affected version or commit, the affected surface, reproduction steps, and evidence sufficient to validate the issue without exposing private material.
