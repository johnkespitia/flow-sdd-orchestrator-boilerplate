# SoftOS SDD Orchestrator Boilerplate

Spanish mirror: [README.es.md](./README.es.md)

Source: `README.en.md`  
Last updated: 2026-05-07

Base template to bootstrap a **Spec-Driven Delivery (SDD)** workspace with `flow` + Tessl + BMAD.

## TL;DR

- `specs/**` is the source of truth.
- `flow` is the SDLC and stack control plane.
- `gateway/` is the central HTTP ingress for webhooks and intents.
- Bootstrap supports two profiles: `master` (full control plane) and `slave` (runner connected to a remote gateway).

## Core capabilities

- Spec-driven lifecycle (`spec`, `plan`, `slice`, `ci`, `release`).
- Workspace orchestration via `flow`.
- Reproducible devcontainer setup.
- Multi-repo routing via `workspace.config.json`.
- Optional agent memory with Engram (consultive only).
- Root CI as the single governance trigger.

## Quick start

1. Create a new repository from this template or bootstrap a fresh workspace with `scripts/bootstrap_workspace.py`.
2. Open in devcontainer.
3. Run:

```bash
python3 ./flow init
python3 ./flow doctor
```

4. Define or update specs under `specs/**`.
5. Execute spec-driven flow:

```bash
python3 ./flow plan <spec-id>
python3 ./flow ci spec --changed --base <base> --head <head>
```

## Bootstrap profiles

- `master`: includes full control plane and central gateway operation.
- `slave`: excludes local gateway and connects to remote gateway using `--gateway-url`.

## Documentation

- Human implementation guide: `docs/softos-human-implementation-step-by-step.md`
- AI full-power usage guide: `docs/softos-ai-fullstack-usage-guide.md`
- Harness core and profiles: `docs/harness-core-and-profiles.md`
- Documentation i18n policy: `docs/documentation-i18n-policy.md`

## i18n policy

- Operational docs are English-canonical with Spanish mirrors.
- For docs under `docs/**`, use `docs/<topic>.md` + `docs/es/<topic>.es.md`.
- Validate with `scripts/ci/validate_docs_i18n.py`.

## Project links

- Contributing: `CONTRIBUTING.md`
- Security: `SECURITY.md`
- Code of conduct: `CODE_OF_CONDUCT.md`

For the complete Spanish operational reference, see `README.es.md`.
