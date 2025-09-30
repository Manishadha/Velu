# Security & Hardening

- Rootless containers; read-only FS; minimal images.
- Secrets only via env/secret stores; never in VCS.
- SBOM; SAST/DAST; dependency & container scans in CI.
- Signed artifacts & rule packs; verified before load.
- Threat-intel mirrored locally for offline scanning.
