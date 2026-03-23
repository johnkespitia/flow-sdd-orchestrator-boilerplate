---
name: project-bootstrap-playbook
description: Use when the user wants to start a new project workspace from this boilerplate, register existing implementation repos, and run the first spec-driven flow end-to-end.
---

# Project Bootstrap Playbook

Use this skill when the user asks to create a new project from the workspace boilerplate or asks for the standard startup flow.

## Outcomes

- Workspace bootstrapped with its own git repo.
- Stack initialized and healthy.
- Existing implementation repo(s) registered.
- First feature spec created, reviewed, approved, and validated.

## Workflow

1. Bootstrap a new workspace.
2. Initialize the workspace stack.
3. Register implementation repo(s).
4. Resolve runtime/skills context.
5. Create and complete first feature spec.
6. Run governance gates (`review`, `approve`, `ci spec`).
7. Implement only in files covered by `targets`.
8. Verify and report clear next steps.

Important: `stack up` only means containers are running. A project is considered ready only when the application process and health endpoint/check are validated.

## Commands Template

```bash
# 1) Create workspace
python3 scripts/bootstrap_workspace.py ~/Projects/<NuevoWorkspace> \
  --project-name "<Proyecto>" \
  --root-repo <proyecto-dev-env> \
  --git-init

# 2) Enter and init
cd ~/Projects/<NuevoWorkspace>
python3 ./flow init
python3 ./flow stack ps

# 3) Register existing repo
python3 ./flow add-project <repo_id> \
  --path <ruta_relativa_repo> \
  --runtime <php|pnpm|go|python> \
  --use-existing-dir

# 4) Runtime/skill context
python3 ./flow skills context --repo <repo_id> --json

# 5) First spec
python3 ./flow spec create <slug> --title "<Titulo>" --repo <repo_id> --runtime <runtime>
python3 ./flow spec review <slug>
python3 ./flow spec approve <slug> --approver <usuario>
python3 ./flow ci spec <slug>
```

## Runtime Readiness Checks (required)

After `flow init` or `flow stack up`, validate app readiness explicitly:

```bash
python3 ./flow stack ps
```

Then run app-level checks by runtime/service:

- PHP:
```bash
python3 ./flow stack exec <compose_service> -- php -v
python3 ./flow stack exec <compose_service> -- sh -lc "test -f /app/public/index.php"
```
- Node:
```bash
python3 ./flow stack exec <compose_service> -- node -v
python3 ./flow stack exec <compose_service> -- sh -lc "ss -lntp | grep -E ':(3000|5173|8000)'"
```
- Python:
```bash
python3 ./flow stack exec <compose_service> -- python3 --version
python3 ./flow stack exec <compose_service> -- sh -lc "ss -lntp | grep -E ':(8000|8001)'"
```

If service exposes a host port, also verify HTTP:

```bash
curl -fsS http://127.0.0.1:<host_port>/healthz || curl -fsS http://127.0.0.1:<host_port>/
```

## Rules

- Keep specs in root `specs/**` as source of truth.
- Implement only what is inside spec `targets`.
- Separate commits by concern:
  - spec/config
  - implementation
  - hardening/fixes
- If production differs from local, validate deployed file version and clear PHP opcache/FPM cache before debugging logic.

## Spec Taxonomy

Use this directory contract when creating specs:

- `specs/000-foundation/**`: workspace operating model and delivery governance.
  - Examples: routing rules, SDLC gates, orchestration contracts, release/infra governance.
- `specs/domains/**`: business-domain contracts and stable cross-feature rules.
  - Examples: entities, invariants, business policies, bounded-context boundaries.
- `specs/features/**`: concrete feature changes to implement now.
  - Examples: one user-facing/API behavior change with specific `targets`.

## Definition of Done

- New workspace running (`flow init` healthy).
- Repo(s) registered in `workspace.config.json`.
- Container is running **and** application readiness checks pass.
- First spec status is `approved`.
- `flow ci spec <slug>` passes.
- Implementation verified in target environment (not only local).
