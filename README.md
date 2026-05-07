# SoftOS SDD Orchestrator Boilerplate

Language: [English](./README.en.md) | [Español](./README.es.md)

Base template to bootstrap a **Spec-Driven Delivery (SDD)** workspace with `flow` + Tessl + BMAD.

## TL;DR

- `specs/**` is the source of truth.
- `flow` is the SDLC and stack control plane.
- `gateway/` is the central HTTP ingress for webhooks and intents.
- Bootstrap supports two profiles: `master` (full control plane) and `slave` (runner connected to a remote gateway).

## Quick Navigation

- [What Is Included](#what-is-included)
- [Recommended Usage](#recommended-usage)
- [Master/Slave Bootstrap Profiles](#masterslave-bootstrap-profiles)
- [After Creating Your Workspace](#after-creating-your-workspace)
- [Integration Gateway](#integration-gateway)
- [New Capabilities](#new-capabilities)
- [Contributing](./CONTRIBUTING.md)
- [Security](./SECURITY.md)
- [Code of Conduct](./CODE_OF_CONDUCT.md)

## New Capabilities

- Reusable Harness Core policy pack in `policies/harness-core/`.
- Project profile contract in `profiles/<profile-id>/profile.json`.
- OSS-safe profile example in `profiles/example-api-ticket/profile.json`.
- Core/profile validator in `scripts/harness/validate_profile.py`.
- Bilingual docs policy (EN default + ES mirror) in `docs/documentation-i18n-policy.md`.

## Harness Profiles: How To Use

Profiles let you bind neutral harness policy to your real project conventions.

1. Start from the example:
   - `profiles/example-api-ticket/profile.json`
2. Create your profile:
   - `profiles/<your-profile-id>/profile.json`
3. Keep private conventions private when needed (internal repo names, channels, links, deploy commands).
4. Validate profile and core contract:
   - `python3 scripts/harness/validate_profile.py --root . --json`
5. Reference profile docs:
   - `profiles/README.md`
   - `docs/harness-core-and-profiles.md`

Minimum profile responsibilities:

- work-item and ticket key conventions
- repository mirror format
- PR labels and review/discovery behavior
- staging/deploy/E2E automation details
- communication ledger expectations

## Feature Map (Added)

- Harness Core policy pack:
  - `policies/harness-core/*`
- Profile contract and example:
  - `profiles/<profile-id>/profile.json`
  - `profiles/example-api-ticket/profile.json`
- Core/profile validator:
  - `scripts/harness/validate_profile.py`
- Human implementation playbook:
  - `docs/softos-human-implementation-step-by-step.md`
- AI full-power operating guide:
  - `docs/softos-ai-fullstack-usage-guide.md`
- Documentation language policy + CI checks:
  - `docs/documentation-i18n-policy.md`
  - `scripts/ci/validate_docs_i18n.py`
- Optional autoskills integration:
  - discover: `python3 ./flow skills discover <query> --json`
  - install: `python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --runtime <runtime>`
  - context: `python3 ./flow skills context --repo <repo> --json`

## What Is Included

- `flow`: workspace CLI for `stack`, `tessl`, `skills`, `bmad`, `memory`, `workflow`, `add-project`, `spec`, `plan`, `slice`, `ci`, `release`, `infra`, `submodule`, `secrets`, `drift`, `status`.
- `workspace.config.json`: configurable routing for repos, targets, and test runners.
- `flowctl/`: internal control-plane modules.
- `workspace.skills.json`: agent capabilities.
- `workspace.runtimes.json`: versioned runtime packs.
- `workspace.capabilities.json`: versioned capabilities catalog.
- `gateway/`: central FastAPI ingress for Jira/Slack/GitHub integrations.
- `.tessl/**`: local SDD tile.
- `_bmad/`: project BMAD runtime.
- `.flow/**`: local SDLC operational state.

## Recommended Usage

### Option 1: use this repository as a template

1. Use GitHub "Use this template".
2. Create your new repository.
3. Clone it.
4. Adjust project naming with `bootstrap_workspace.py` if needed.

### Option 2: generate a clean isolated project from this boilerplate

```bash
python3 scripts/bootstrap_workspace.py /path/to/new-workspace \
  --project-name "Acme Platform" \
  --root-repo acme-dev-env \
  --git-init
```

## Master/Slave Bootstrap Profiles

- `master`: includes full control plane and `gateway/` for central operations.
- `slave`: excludes local `gateway/` and connects to a remote gateway via `--gateway-url`.

## After Creating Your Workspace

```bash
python3 ./flow init
python3 ./flow doctor
python3 ./flow plan <spec-id>
python3 ./flow ci spec --changed --base <base> --head <head>
```

## Integration Gateway

Use `gateway/` for webhooks/intents and centralized orchestration of external systems.

## Documentation

- Human implementation guide: `docs/softos-human-implementation-step-by-step.md`
- AI full-power usage guide: `docs/softos-ai-fullstack-usage-guide.md`
- Harness core/profiles: `docs/harness-core-and-profiles.md`
- i18n docs policy: `docs/documentation-i18n-policy.md`

## i18n Policy

- English is canonical by default.
- Spanish mirrors are required for operational/user-facing docs.
- Use `docs/<topic>.md` + `docs/es/<topic>.es.md`.
- Validate with `scripts/ci/validate_docs_i18n.py`.
