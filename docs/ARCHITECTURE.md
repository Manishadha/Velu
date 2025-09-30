# Velu Architecture (2025)

- **orchestrator/**: agent contracts, router client, scheduler, state.
- **services/**: model-router, policy-engine, feedback-monitor (sidecars).
- **agents/**: planning, architecture, codegen, executor, debug, security, ui, build, deploy.
- **data/**: models (immutable), pointers (current), rules (versioned), threat-intel (mirrors).
- **ops/**: env configs (hot-reload), Docker, CI/CD, optional Kubernetes.

**Update Strategy (no code change):** stable APIs + adapters, config-driven behavior, sidecars, immutable artifacts with movable pointers; canary/shadow/blue-green.
