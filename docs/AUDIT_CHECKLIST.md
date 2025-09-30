# Audit Checklist

- Repo isolation: unique SSH key, dedicated DB name/instance (if used).
- Secrets excluded; .env.example present; env files not committed.
- CI runs build, tests, lint, security scans; produces SBOM.
- Docs: ARCHITECTURE, SECURITY, HANDOVER, COMPLIANCE, CHANGELOG.
- Rule packs signed; model registry & channels defined.
- Scripts: setup/run/test/lint/audit are idempotent.
