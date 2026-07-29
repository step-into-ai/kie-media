# Security policy

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials, paid KIE tasks, uploaded media, or private manifests. Use GitHub's **Report a vulnerability** / private security advisory feature for this repository. Include affected version, reproduction steps, impact, and a suggested mitigation when available.

Do not include real API keys, authorization headers, private media, or task payloads in the report. Redact them before attaching logs.

## Security model

- `KIE_API_KEY` remains local and is never written to history or manifests.
- Inputs are validated before upload and task creation.
- Paid task creation is not automatically retried after ambiguous failure.
- Agent plans are bounded by `--max-jobs`, fingerprinted, checkpointed, and concurrency-locked.
- Manifests, history, locks, and downloaded assets are owner-only where the operating system supports POSIX permissions.
- Planning and offline evals require no network and no credentials.
- Live model discovery never calls the paid KIE API and does not require `KIE_API_KEY`.
- Discovery accepts only bounded HTTPS documentation from `docs.kie.ai`; redirects, external hosts, YAML aliases, untyped fields, missing model IDs, and unusable `createTask` schemas are rejected.
- Remote prose is never treated as an agent prompt or instruction. Only validated model IDs, field types, enums, defaults, and limits are cached.
- Cache updates are atomic and owner-only; invalid refreshes preserve the last-known-good schema.
- Preferences and observed-credit history remain local, private, and contain no credentials.

This project uses KIE.ai as an external processor. Users are responsible for reviewing KIE's current terms, privacy policy, content rules, and pricing before uploading sensitive media or running generation.
