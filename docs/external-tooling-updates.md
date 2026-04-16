# External Tooling Updates

SoftOS uses external tooling in three separate layers:

- container-installed binaries: pnpm, Tessl CLI, BMAD CLI and Engram
- versioned workspace assets: `.tessl/**`, `_bmad/**`, `.agents/skills/**`, `workspace.skills.json`
- local operational state: `.flow/memory/engram`, `.flow/reports/**`, `.flow/state/**`

Keep these layers separate. Updating a binary is not the same as accepting generated assets, and updating memory state is never a source-of-truth change.

## Default Policy

The workspace image defaults to the latest upstream tool versions at build time:

- `PNPM_VERSION=latest`
- `TESSL_CLI_VERSION=latest`
- `BMAD_METHOD_VERSION=latest`
- `ENGRAM_VERSION=latest`

This keeps development workspaces current when the image is rebuilt. For staging, production, demos, or release branches, override the build args with explicit versions so the toolchain is reproducible.

## Update To Latest

Use a no-cache build when the intent is to refresh `latest`; otherwise Docker can reuse a cached layer and keep the previous binary. SoftOS resolves Compose dynamically: it prefers the `docker compose` plugin when available and falls back to standalone `docker-compose`.

```bash
python3 ./flow stack build --no-cache
python3 ./flow stack up --build
python3 ./flow doctor --json
python3 ./flow workflow doctor --json
python3 ./flow skills doctor --json
python3 ./flow memory doctor --json
python3 ./flow memory smoke --json
```

If the stack is already running, rebuild first and then recreate the `workspace` service through the normal stack flow.

## Pin Versions

Pin versions with Docker build args when reproducibility matters:

```bash
docker compose \
  -f .devcontainer/docker-compose.yml \
  build \
  --build-arg PNPM_VERSION=<version> \
  --build-arg TESSL_CLI_VERSION=<version> \
  --build-arg BMAD_METHOD_VERSION=<version> \
  --build-arg ENGRAM_VERSION=<tag> \
  workspace
```

Examples:

- `TESSL_CLI_VERSION=latest` installs `@tessl/cli@latest`.
- `BMAD_METHOD_VERSION=latest` installs `bmad-method@latest`.
- `ENGRAM_VERSION=latest` resolves the latest GitHub release.
- `ENGRAM_VERSION=v1.11.0` resolves the matching GitHub release tag.

Do not pin Engram to a tag unless that tag exists in `Gentleman-Programming/engram` releases and provides a Linux asset for the container architecture.

## Tessl

Tessl has two update surfaces:

- CLI binary: installed in the devcontainer from npm.
- Native runtime binary: downloaded by the Tessl npm wrapper and prewarmed during image build.
- Local SDD content: `.tessl/**` and `tessl.json`.

Validate after updating:

```bash
python3 ./flow tessl -- --help
python3 ./flow workflow doctor --json
python3 ./flow skills sync --dry-run
```

If Tessl-generated or Tessl-imported content changes `.tessl/**`, treat it as a normal versioned diff: review it under a spec, run `flow ci spec`, and commit only expected changes.

## BMAD

BMAD has two update surfaces:

- CLI binary: installed in the devcontainer from npm.
- Project runtime assets: `_bmad/**`.

Validate after updating:

```bash
python3 ./flow bmad -- --help
python3 ./flow bmad -- status
python3 ./flow workflow doctor --json
```

If `bmad install` or another BMAD command changes `_bmad/**`, review the diff before committing. `_bmad-output/**` is operational output and should not be treated as canonical source.

## Engram

Engram has two update surfaces:

- CLI binary: installed in the devcontainer from GitHub Releases.
- Project-scoped memory DB: `.flow/memory/engram`.

Back up memory before runtime upgrades:

```bash
python3 ./flow memory backup --json
python3 ./flow memory doctor --json
python3 ./flow memory smoke --json
```

Restore only from reviewed exports:

```bash
python3 ./flow memory import .flow/memory/backups/<file>.json --json
python3 ./flow memory import .flow/memory/backups/<file>.json --confirm --json
```

Engram memory is consultive. It must not override specs, approvals, plans, CI evidence, release manifests, or human gates.

## Skills

Workspace skills are governed by `workspace.skills.json`.

Useful commands:

```bash
python3 ./flow skills list --json
python3 ./flow skills doctor --json
python3 ./flow skills sync --dry-run
python3 ./flow skills sync --name <skill-name>
python3 ./flow skills discover <query> --limit 10 --json
python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --runtime <runtime>
```

Most local SoftOS playbooks intentionally use `"sync": false`; they should not be overwritten by a broad sync. Use `--name` when you intentionally want to refresh a specific entry.

## Release Checklist

Before declaring a toolchain update complete:

- `python3 ./flow doctor --json`
- `python3 ./flow workflow doctor --json`
- `python3 ./flow skills doctor --json`
- `python3 ./flow skills sync --dry-run`
- `python3 ./flow memory doctor --json`
- `python3 ./flow memory smoke --json`
- `python3 ./flow ci spec <toolchain-update-spec> --json`

If assets changed, include the reviewed diffs in the release. If only the image rebuild changed binaries, record the observed versions in the release evidence.
