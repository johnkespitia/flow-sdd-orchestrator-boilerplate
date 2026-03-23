# Runtime & Capability Playbook

Use this when alignment requires new runtime or capability packs.

## 1) Runtime Pack Lifecycle

### Create

1. Add `runtimes/<runtime>.runtime.json`.
2. Register runtime in `workspace.runtimes.json`.
3. Ensure runtime is enabled.

### Minimum Runtime Contract

- `runtime_kind` (`project` or `service` when applicable)
- `target_roots`
- `default_targets`
- `test_runner`
- `test_hint`
- `test_required_roots`
- `placeholder_dirs`
- `placeholder_files`
- `agent_skill_refs`
- `ci`
- `compose` (or `null`)

For `compose`, include when applicable:

- `default_port`
- `command`
- `working_dir`
- `mount_target`
- `networks`

### Validate

```bash
python3 ./flow doctor
python3 ./flow skills doctor
```

Then register a sample project:

```bash
python3 ./flow add-project <repo_id> --runtime <runtime> --path <path>
```

If service must be exposed on host:

```bash
python3 ./flow add-project <repo_id> --runtime <runtime> --path <path> --port <host_port>
python3 ./flow stack up
python3 ./flow stack ps
```

Expected in `stack ps`: `0.0.0.0:<host_port>-><container_port>/tcp`.

## Readiness Is Mandatory

Container state alone is insufficient. Validate app-level readiness after `stack up`.

Preferred approach:

- Define checks in `workspace.preflight.json`.
- Execute `scripts/preflight_env.sh --build` (and optionally `--run-migrations`).
- Keep readiness policy repo-specific and technology-agnostic.

### Generic pattern

1. Process/listener check inside container.
2. Endpoint check from host (when port exposed).

Examples:

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

Host HTTP:

```bash
curl -fsS http://127.0.0.1:<host_port>/healthz || curl -fsS http://127.0.0.1:<host_port>/
```

## 2) Capability Pack Lifecycle

### Create

1. Add `capabilities/<capability>.capability.json`.
2. Register capability in `workspace.capabilities.json`.
3. Ensure required runtimes are explicitly declared.

### Minimum Capability Contract

- `title`
- `summary`
- `required_runtimes`
- `target_roots`
- `agent_skill_refs`
- `placeholder_files`
- optional `compose_override`

### Validate

Run capability through `flow add-project` with matching runtime:

```bash
python3 ./flow add-project <repo_id> --runtime <runtime> --capabilities <capability>
```

## 3) Skill Installation & Binding

Discover/install:

```bash
python3 ./flow skills discover <query> --limit 10 --json
python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --name <workspace/skill-name> --runtime <runtime>
python3 ./flow skills doctor
```

Binding rules:

- runtime-level defaults in `runtimes/<runtime>.runtime.json`
- workspace-level entries in `workspace.skills.json`
- repo-level effective list in `workspace.config.json` (`agent_skill_refs`)

## 4) Common Failure Modes

- Runtime references unknown `agent_skill_refs`.
- Capability requires runtime not available in `workspace.runtimes.json`.
- `targets` in foundation specs point outside repo `target_roots`.
- Test runner configured but no valid `[@test]` file.
- Service expected to be reachable from host but has no port mapping in compose output.
- Container reports `Up` but app process is not healthy or endpoint check fails.

Always close these before approval.
