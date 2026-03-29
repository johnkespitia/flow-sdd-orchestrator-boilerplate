---
name: softos-stack-compose-federation
description: Use when implementation repos already provide their own docker-compose.yml or compose.yaml and SoftOS must include those compose files instead of duplicating services in the root devcontainer compose.
---

# SoftOS Stack Compose Federation

Use this skill when a project repo already has its own Docker Compose file.

## Goal

Keep the workspace control plane compose for shared services, but include project compose files dynamically so SoftOS does not duplicate implementation services.

## Rules

- Do not copy a repo service into `.devcontainer/docker-compose.yml` if the repo already has:
  - `docker-compose.yml`
  - `docker-compose.yaml`
  - `compose.yml`
  - `compose.yaml`
  - `.devcontainer/docker-compose.yml`
  - `.devcontainer/docker-compose.yaml`
- Record the compose source in `workspace.config.json` as `compose_file` when known.
- Build Docker commands with every compose file in the stack, not only the root compose.
- Preflight checks must validate the combined compose surface.

## Workspace behavior

Expected model:

1. Root compose remains the base file.
2. Repo compose files are appended as extra `-f` arguments.
3. `flow stack` and CI use the combined compose list.
4. `stack apply` avoids injecting a duplicate service into the root compose when the repo compose exists.

## Files to touch

- `flowctl/stack.py`
- `flowctl/stack_design.py`
- `flow`
- `scripts/preflight_env.sh`

## Validation checklist

1. `compose_base_command()` renders all compose files in order.
2. A repo with its own compose file is registered with `compose_file`.
3. `stack apply` reports external compose usage instead of adding a duplicate service.
4. Preflight still finds `compose_service` in the combined compose config.

## Useful checks

```bash
python3 -m pytest -q flowctl/test_stack_compose_files.py
bash -n scripts/preflight_env.sh
```
