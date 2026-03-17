from __future__ import annotations

import argparse


def build_parser(
    *,
    commands: dict[str, object],
    provider_categories,
    repo_names: list[str],
    implementation_repos,
    available_runtime_names,
    available_service_runtime_names,
    available_capability_names,
    runtime_error_type,
    root,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workspace flow CLI for spec-driven orchestration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate workspace layout.")
    doctor.add_argument("--json", action="store_true", help="Print the doctor result as JSON.")
    doctor.set_defaults(func=commands["doctor"])

    init = subparsers.add_parser("init", help="Bootstrap first run: sync secrets, start the stack and print runtime status.")
    init.add_argument("--build", action="store_true", help="Build images before starting the stack.")
    init.add_argument("--skip-doctor", action="store_true", help="Skip the initial `flow doctor` check.")
    init.add_argument("--skip-stack", action="store_true", help="Only materialize secrets and skip `stack up`.")
    init.add_argument("--force-secrets-sync", action="store_true", help="Regenerate `.devcontainer/.env.generated` even if it already exists.")
    init.set_defaults(func=commands["init"])

    stack = subparsers.add_parser("stack", help="Operate the devcontainer stack from the control plane.")
    stack_subparsers = stack.add_subparsers(dest="stack_command", required=True)
    for name, help_text in [("doctor", "Show resolved Docker Compose context."), ("ps", "Show stack services.")]:
        parser_item = stack_subparsers.add_parser(name, help=help_text)
        parser_item.set_defaults(func=commands[f"stack_{name}"])

    stack_up = stack_subparsers.add_parser("up", help="Start the stack in detached mode.")
    stack_up.add_argument("--build", action="store_true", help="Build images before starting.")
    stack_up.set_defaults(func=commands["stack_up"])

    stack_down = stack_subparsers.add_parser("down", help="Stop the stack.")
    stack_down.add_argument("-v", "--volumes", action="store_true", help="Also remove volumes.")
    stack_down.add_argument("--rmi-local", action="store_true", help="Also remove locally built images (`--rmi local`).")
    stack_down.set_defaults(func=commands["stack_down"])

    stack_build = stack_subparsers.add_parser("build", help="Build stack images.")
    stack_build.add_argument("--no-cache", action="store_true", help="Build without cache.")
    stack_build.set_defaults(func=commands["stack_build"])

    stack_logs = stack_subparsers.add_parser("logs", help="Stream or print stack logs.")
    stack_logs.add_argument("service", nargs="?", help="Optional service name.")
    stack_logs.add_argument("--follow", dest="follow", action="store_true", help="Follow the log stream (default behaviour).")
    stack_logs.add_argument("--once", dest="follow", action="store_false", help="Print logs once without following the stream.")
    stack_logs.set_defaults(func=commands["stack_logs"], follow=True)

    stack_sh = stack_subparsers.add_parser("sh", help="Open a shell inside a service.")
    stack_sh.add_argument("service", nargs="?", help="Service name. Defaults to workspace.")
    stack_sh.add_argument("--shell", default="bash", help="Shell executable to launch.")
    stack_sh.set_defaults(func=commands["stack_sh"])

    stack_exec = stack_subparsers.add_parser("exec", help="Execute an arbitrary command inside a service.")
    stack_exec.add_argument("service", help="Service name.")
    stack_exec.add_argument("--no-tty", action="store_true", help="Disable TTY allocation.")
    stack_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute.")
    stack_exec.set_defaults(func=commands["stack_exec"])

    stack_design = stack_subparsers.add_parser("design", help="Draft a stack spec from a prompt or derive a stack manifest from an approved spec.")
    stack_design_source = stack_design.add_mutually_exclusive_group(required=True)
    stack_design_source.add_argument("--prompt", help="Natural-language description used to draft a stack spec.")
    stack_design_source.add_argument("--spec", help="Approved spec path or slug used as canonical source.")
    stack_design.add_argument("--slug", help="Optional slug for the prompt-generated spec draft.")
    stack_design.add_argument("--title", help="Optional title for the prompt-generated spec draft.")
    stack_design.add_argument("--force", action="store_true", help="Overwrite an existing prompt-generated draft spec.")
    stack_design.add_argument("--json", action="store_true", help="Print the designed manifest as JSON.")
    stack_design.set_defaults(func=commands["stack_design"])

    stack_plan = stack_subparsers.add_parser("plan", help="Summarize actions required by `workspace.stack.json`.")
    stack_plan.add_argument("--spec", help="Approved spec path or slug. If provided, derive `workspace.stack.json` first.")
    stack_plan.add_argument("--json", action="store_true", help="Print the plan as JSON.")
    stack_plan.set_defaults(func=commands["stack_plan"])

    stack_apply = stack_subparsers.add_parser("apply", help="Apply `workspace.stack.json` to the workspace scaffold.")
    stack_apply.add_argument("--spec", help="Approved spec path or slug. If provided, derive `workspace.stack.json` first.")
    stack_apply.add_argument("--json", action="store_true", help="Print the apply result as JSON.")
    stack_apply.set_defaults(func=commands["stack_apply"])

    tessl = subparsers.add_parser("tessl", help="Run Tessl through the canonical workspace environment.")
    tessl.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to Tessl.")
    tessl.set_defaults(func=commands["tessl"])

    bmad = subparsers.add_parser("bmad", help="Run BMAD through the canonical workspace environment.")
    bmad.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the BMAD command.")
    bmad.set_defaults(func=commands["bmad"])

    skills = subparsers.add_parser("skills", help="Manage assistant skills through a versioned workspace manifest.")
    skills_subparsers = skills.add_subparsers(dest="skills_command", required=True)
    for name, help_text in [
        ("doctor", "Validate `workspace.skills.json` and skill runtimes."),
        ("list", "List skill entries from `workspace.skills.json`."),
    ]:
        parser_item = skills_subparsers.add_parser(name, help=help_text)
        parser_item.add_argument("--json", action="store_true", help="Print the result as JSON.")
        parser_item.set_defaults(func=commands[f"skills_{name}"])

    skills_add = skills_subparsers.add_parser("add", help="Register a skill entry in `workspace.skills.json`.")
    skills_add.add_argument("name", help="Stable manifest name for the skill entry.")
    skills_add.add_argument("--provider", required=True, help="Provider id: `tessl` or `skills-sh`.")
    skills_add.add_argument("--kind", help="Entry kind. Defaults to `tile` for Tessl and `package` for skills-sh.")
    skills_add.add_argument("--source", required=True, help="Registry ref, GitHub source, or local relative path.")
    skills_add.add_argument("--arg", action="append", help="Provider-specific argument persisted with the entry.")
    skills_add.add_argument("--require", action="append", help="Binary required by this skill entry. Repeatable.")
    skills_add.add_argument("--notes", help="Optional human note stored in the manifest.")
    skills_add.add_argument("--required", action="store_true", help="Mark the entry as required for the workspace.")
    skills_add.add_argument("--disabled", action="store_true", help="Create the entry disabled.")
    skills_add.add_argument("--no-sync", action="store_true", help="Exclude the entry from default `skills sync`.")
    skills_add.set_defaults(func=commands["skills_add"])

    skills_sync = skills_subparsers.add_parser("sync", help="Synchronize registered skills through their providers.")
    skills_sync.add_argument("--provider", help="Optional provider filter: `tessl` or `skills-sh`.")
    skills_sync.add_argument("--name", action="append", help="Optional manifest entry name to sync. Repeatable.")
    skills_sync.add_argument("--dry-run", action="store_true", help="Print and record commands without executing them.")
    skills_sync.add_argument("--json", action="store_true", help="Print the sync report as JSON.")
    skills_sync.set_defaults(func=commands["skills_sync"])

    providers = subparsers.add_parser("providers", help="Inspect provider adapters for release and infrastructure.")
    providers_subparsers = providers.add_subparsers(dest="providers_command", required=True)
    for name, help_text in [("doctor", "Validate `workspace.providers.json` and entrypoints."), ("list", "List configured providers.")]:
        parser_item = providers_subparsers.add_parser(name, help=help_text)
        parser_item.add_argument("--category", choices=provider_categories(), help="Optional category filter.")
        parser_item.add_argument("--json", action="store_true", help="Print the result as JSON.")
        parser_item.set_defaults(func=commands[f"providers_{name}"])

    submodule = subparsers.add_parser("submodule", help="Validate and synchronize Git submodule pointers.")
    submodule_subparsers = submodule.add_subparsers(dest="submodule_command", required=True)
    submodule_doctor = submodule_subparsers.add_parser("doctor", help="Inspect configured submodule repos.")
    submodule_doctor.add_argument("--json", action="store_true", help="Print the doctor result as JSON.")
    submodule_doctor.set_defaults(func=commands["submodule_doctor"])
    submodule_sync = submodule_subparsers.add_parser("sync", help="Run `git submodule sync/update` and stage gitlinks.")
    submodule_sync.add_argument("--no-stage", action="store_true", help="Do not stage gitlinks after sync.")
    submodule_sync.add_argument("--json", action="store_true", help="Print the sync report as JSON.")
    submodule_sync.set_defaults(func=commands["submodule_sync"])

    worktree = subparsers.add_parser("worktree", help="Create root worktrees and hydrate submodules safely.")
    worktree_subparsers = worktree.add_subparsers(dest="worktree_command", required=True)
    worktree_create = worktree_subparsers.add_parser(
        "create",
        help="Create a root worktree and hydrate submodules serially.",
    )
    worktree_create.add_argument("name", help="Directory name under `.worktrees/` for the new worktree.")
    worktree_create.add_argument("--branch", help="Branch to create. Defaults to `demo/<name>`.")
    worktree_create.add_argument(
        "--from-ref",
        dest="from_ref",
        default="HEAD",
        help="Base ref used by `git worktree add`. Defaults to `HEAD`.",
    )
    worktree_create.add_argument("--json", action="store_true", help="Print the creation report as JSON.")
    worktree_create.set_defaults(func=commands["worktree_create"])

    secrets = subparsers.add_parser("secrets", help="Resolve secrets through provider adapters without storing them in Git.")
    secrets_subparsers = secrets.add_subparsers(dest="secrets_command", required=True)
    for name, help_text in [("doctor", "Validate `workspace.secrets.json` and secret providers."), ("list", "List configured secret targets.")]:
        parser_item = secrets_subparsers.add_parser(name, help=help_text)
        parser_item.add_argument("--json", action="store_true", help="Print the result as JSON.")
        parser_item.set_defaults(func=commands[f"secrets_{name}"])

    secrets_sync = secrets_subparsers.add_parser("sync", help="Materialize secret targets into local generated files.")
    secrets_sync.add_argument("--target", action="append", help="Target name to sync. Repeatable.")
    secrets_sync.add_argument("--dry-run", action="store_true", help="Resolve targets without writing files.")
    secrets_sync.add_argument("--json", action="store_true", help="Print the sync report as JSON.")
    secrets_sync.set_defaults(func=commands["secrets_sync"])

    secrets_exec = secrets_subparsers.add_parser("exec", help="Execute a command with secrets injected in the environment.")
    secrets_exec.add_argument("--target", action="append", help="Target name to load. Repeatable.")
    secrets_exec.add_argument("--json", action="store_true", help="Print resolved env keys instead of executing.")
    secrets_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute after `--`.")
    secrets_exec.set_defaults(func=commands["secrets_exec"])

    secrets_scan = secrets_subparsers.add_parser("scan", help="Scan tracked, changed or staged files for leaked secrets.")
    secrets_scan.add_argument("--repo", choices=repo_names, help="Optional repo id from `workspace.config.json`.")
    secrets_scan.add_argument("--all", action="store_true", help="Scan tracked files across every configured repo.")
    secrets_scan.add_argument("--staged", action="store_true", help="Scan only staged files in the selected repo.")
    secrets_scan.add_argument("--json", action="store_true", help="Print the scan report as JSON.")
    secrets_scan.set_defaults(func=commands["secrets_scan"])

    drift = subparsers.add_parser("drift", help="Run static drift checks between specs and implementation surfaces.")
    drift_subparsers = drift.add_subparsers(dest="drift_command", required=True)
    drift_check = drift_subparsers.add_parser("check", help="Validate targets, test refs and declared contracts.")
    drift_check.add_argument("spec", nargs="?", help="Optional spec path or slug.")
    drift_check.add_argument("--all", action="store_true", help="Validate every spec under `specs/**`.")
    drift_check.add_argument("--changed", action="store_true", help="Validate only specs changed in git diff.")
    drift_check.add_argument("--base", help="Base git ref for `--changed`.")
    drift_check.add_argument("--head", help="Head git ref for `--changed`.")
    drift_check.add_argument("--json", action="store_true", help="Print the drift report as JSON.")
    drift_check.set_defaults(func=commands["drift_check"])

    contract = subparsers.add_parser("contract", help="Verify generated contracts against implementation surfaces.")
    contract_subparsers = contract.add_subparsers(dest="contract_command", required=True)
    contract_verify = contract_subparsers.add_parser("verify", help="Verify declared contracts against implementation files.")
    contract_verify.add_argument("spec", nargs="?", help="Optional spec path or slug.")
    contract_verify.add_argument("--all", action="store_true", help="Verify every spec under `specs/**`.")
    contract_verify.add_argument("--changed", action="store_true", help="Verify only specs changed in git diff.")
    contract_verify.add_argument("--base", help="Base git ref for `--changed`.")
    contract_verify.add_argument("--head", help="Head git ref for `--changed`.")
    contract_verify.add_argument("--json", action="store_true", help="Print the verification report as JSON.")
    contract_verify.set_defaults(func=commands["contract_verify"])

    ci = subparsers.add_parser("ci", help="Run spec-driven CI checks from the control plane.")
    ci_subparsers = ci.add_subparsers(dest="ci_command", required=True)
    ci_spec = ci_subparsers.add_parser("spec", help="Validate canonical specs for CI.")
    ci_spec.add_argument("spec", nargs="?", help="Optional spec path or slug.")
    ci_spec.add_argument("--all", action="store_true", help="Validate every spec under `specs/**`.")
    ci_spec.add_argument("--changed", action="store_true", help="Validate only specs changed in git diff.")
    ci_spec.add_argument("--base", help="Base git ref for `--changed`.")
    ci_spec.add_argument("--head", help="Head git ref for `--changed`.")
    ci_spec.add_argument("--json", action="store_true", help="Print the CI report as JSON.")
    ci_spec.set_defaults(func=commands["ci_spec"])

    ci_repo = ci_subparsers.add_parser("repo", help="Run repo-level CI checks.")
    ci_repo.add_argument("repo", nargs="?", choices=implementation_repos(), help="Repo id from `workspace.config.json`.")
    ci_repo.add_argument("--all", action="store_true", help="Run repo CI for every implementation repo.")
    ci_repo.add_argument("--spec", help="Optional spec slug to scope the report.")
    ci_repo.add_argument("--base", help="Optional git base ref.")
    ci_repo.add_argument("--head", help="Optional git head ref.")
    ci_repo.add_argument("--skip-install", action="store_true", help="Skip dependency installation before CI commands.")
    ci_repo.add_argument("--json", action="store_true", help="Print the CI report as JSON.")
    ci_repo.set_defaults(func=commands["ci_repo"])

    ci_integration = ci_subparsers.add_parser("integration", help="Run stack-level smoke checks.")
    ci_integration.add_argument("--profile", default="smoke", help="Integration profile label.")
    ci_integration.add_argument("--auto-up", action="store_true", help="Start the stack if it is not active.")
    ci_integration.add_argument("--build", action="store_true", help="Build images if `--auto-up` starts the stack.")
    ci_integration.add_argument("--json", action="store_true", help="Print the integration report as JSON.")
    ci_integration.set_defaults(func=commands["ci_integration"])

    release = subparsers.add_parser("release", help="Manage release manifests and promotions.")
    release_subparsers = release.add_subparsers(dest="release_command", required=True)
    release_cut = release_subparsers.add_parser("cut", help="Create a release manifest.")
    release_cut.add_argument("--version", help="Explicit release version. Defaults to a UTC timestamp.")
    release_cut.add_argument("--spec", action="append", help="Feature spec slug or path to include. Repeatable.")
    release_cut.add_argument("--all-approved", action="store_true", help="Include every approved unreleased feature spec.")
    release_cut.add_argument("--force", action="store_true", help="Overwrite an existing manifest for the same version.")
    release_cut.add_argument("--json", action="store_true", help="Print the cut result as JSON.")
    release_cut.set_defaults(func=commands["release_cut"])

    release_manifest = release_subparsers.add_parser("manifest", help="Show or print a release manifest.")
    release_manifest.add_argument("--version", required=True, help="Release version.")
    release_manifest.add_argument("--json", action="store_true", help="Print the manifest payload as JSON.")
    release_manifest.set_defaults(func=commands["release_manifest"])

    release_status = release_subparsers.add_parser("status", help="Summarize a release manifest.")
    release_status.add_argument("--version", required=True, help="Release version.")
    release_status.add_argument("--json", action="store_true", help="Print the release summary as JSON.")
    release_status.set_defaults(func=commands["release_status"])

    release_promote = release_subparsers.add_parser("promote", help="Promote a release to an environment.")
    release_promote.add_argument("--version", required=True, help="Release version.")
    release_promote.add_argument("--env", dest="environment", required=True, choices=["preview", "staging", "production"])
    release_promote.add_argument("--provider", help="Optional release provider id. Defaults to workspace.providers.json.")
    release_promote.add_argument("--approver", help="Required for staging and production promotions.")
    release_promote.add_argument("--json", action="store_true", help="Print the promotion result as JSON.")
    release_promote.set_defaults(func=commands["release_promote"])

    infra = subparsers.add_parser("infra", help="Plan and apply infrastructure governed by specs.")
    infra_subparsers = infra.add_subparsers(dest="infra_command", required=True)
    infra_plan = infra_subparsers.add_parser("plan", help="Create an infrastructure plan from a spec.")
    infra_plan.add_argument("spec", help="Spec path or slug.")
    infra_plan.add_argument("--env", dest="environment", required=True, help="Target environment.")
    infra_plan.add_argument("--provider", help="Optional infra provider id. Defaults to workspace.providers.json.")
    infra_plan.add_argument("--json", action="store_true", help="Print the infra plan report as JSON.")
    infra_plan.set_defaults(func=commands["infra_plan"])

    infra_apply = infra_subparsers.add_parser("apply", help="Apply a previously generated infrastructure plan.")
    infra_apply.add_argument("spec", help="Spec path or slug.")
    infra_apply.add_argument("--env", dest="environment", required=True, help="Target environment.")
    infra_apply.add_argument("--provider", help="Optional infra provider id. Defaults to workspace.providers.json.")
    infra_apply.add_argument("--approver", help="Required for staging and production environments.")
    infra_apply.add_argument("--json", action="store_true", help="Print the infra apply report as JSON.")
    infra_apply.set_defaults(func=commands["infra_apply"])

    infra_status = infra_subparsers.add_parser("status", help="Show recorded infra plans/applies for a feature.")
    infra_status.add_argument("spec", help="Spec path or slug.")
    infra_status.add_argument("--json", action="store_true", help="Print the infra status as JSON.")
    infra_status.set_defaults(func=commands["infra_status"])

    add_project = subparsers.add_parser("add-project", help="Register a new implementation repo and optional service in the workspace.")
    add_project.add_argument("name", help="Project id used by flow and by `--repo` in specs.")
    add_project.add_argument("--path", help="Relative path from the workspace root. Defaults to the project id.")
    try:
        runtime_help = ", ".join(available_runtime_names(root))
    except runtime_error_type:
        runtime_help = "manifest unavailable"
    add_project.add_argument("--runtime", default="generic", help=f"Runtime pack id for targets, scaffolding and compose integration. Disponibles: {runtime_help}.")
    add_project.add_argument("--service-name", help="Compose service name. Defaults to the project id.")
    add_project.add_argument("--port", type=int, help="Optional port to expose for the new compose service.")
    add_project.add_argument("--no-compose", action="store_true", help="Skip compose service scaffolding even if the runtime provides a template.")
    add_project.add_argument("--use-existing-dir", action="store_true", help="Allow registering an existing non-empty directory instead of requiring a fresh placeholder.")
    add_project.add_argument("--target-root", action="append", help="Override target roots. Repeat to define multiple roots.")
    add_project.add_argument("--default-target", action="append", help="Override default target patterns. Repeat to define multiple patterns.")
    add_project.add_argument("--test-runner", choices=["none", "php", "pnpm", "pytest", "go"], help="Override the test runner used by `flow slice verify`.")
    add_project.add_argument("--test-hint", help="Override the default `[@test]` hint for this project.")
    add_project.add_argument("--ci-install", help="Override the install command used by `flow ci repo` for this project.")
    add_project.add_argument("--ci-lint", help="Override the lint command used by `flow ci repo` for this project.")
    add_project.add_argument("--ci-test", help="Override the test command used by `flow ci repo` for this project.")
    add_project.add_argument("--ci-build", help="Override the build command used by `flow ci repo` for this project.")
    add_project.add_argument(
        "--no-ci-step",
        action="append",
        choices=["install", "lint", "test", "build"],
        help="Disable a runtime-provided CI step. Repeat to disable multiple steps.",
    )
    add_project.set_defaults(func=commands["add_project"])

    spec = subparsers.add_parser("spec", help="Manage canonical specs.")
    spec_subparsers = spec.add_subparsers(dest="spec_command", required=True)
    spec_create = spec_subparsers.add_parser("create", help="Create a root feature spec.")
    spec_create.add_argument("slug", help="Feature slug in kebab-case or human text.")
    spec_create.add_argument("--title", required=True, help="Human-readable title.")
    spec_create.add_argument("--repo", action="append", choices=repo_names, help="Target repo. Repeat to create cross-repo specs.")
    try:
        service_choices = available_service_runtime_names(root)
        runtime_choices = [candidate for candidate in available_runtime_names(root) if candidate not in service_choices]
        capability_choices = available_capability_names(root)
    except Exception:
        runtime_choices = []
        service_choices = []
        capability_choices = []
    spec_create.add_argument(
        "--runtime",
        action="append",
        choices=runtime_choices or None,
        help="Declare a required project runtime. Repeatable.",
    )
    spec_create.add_argument(
        "--service",
        action="append",
        choices=service_choices or None,
        help="Declare a required service runtime. Repeatable.",
    )
    spec_create.add_argument(
        "--capability",
        action="append",
        choices=capability_choices or None,
        help="Declare a required capability. Repeatable.",
    )
    spec_create.add_argument(
        "--depends-on",
        action="append",
        help="Declare prerequisite specs by slug or path. Repeatable.",
    )
    spec_create.set_defaults(func=commands["spec_create"])

    spec_review = spec_subparsers.add_parser("review", help="Create a spec review report.")
    spec_review.add_argument("spec", help="Spec path or slug.")
    spec_review.add_argument("--json", action="store_true", help="Print a structured review result.")
    spec_review.set_defaults(func=commands["spec_review"])

    spec_approve = spec_subparsers.add_parser("approve", help="Approve a canonical spec.")
    spec_approve.add_argument("spec", help="Spec path or slug.")
    spec_approve.add_argument("--approver", help="Identity recorded for the approval. Defaults to FLOW_APPROVER/USER.")
    spec_approve.set_defaults(func=commands["spec_approve"])

    spec_generate_contracts = spec_subparsers.add_parser("generate-contracts", help="Generate derived contract artifacts from `json contract` blocks in a spec.")
    spec_generate_contracts.add_argument("spec", help="Spec path or slug.")
    spec_generate_contracts.add_argument("--json", action="store_true", help="Print generated artifacts as JSON.")
    spec_generate_contracts.set_defaults(func=commands["spec_generate_contracts"])

    plan = subparsers.add_parser("plan", help="Create a default worktree plan from a spec.")
    plan.add_argument("spec", help="Spec path or slug.")
    plan.set_defaults(func=commands["plan"])

    slice_cmd = subparsers.add_parser("slice", help="Prepare slice execution or verification.")
    slice_subparsers = slice_cmd.add_subparsers(dest="slice_command", required=True)
    slice_start = slice_subparsers.add_parser("start", help="Prepare a slice handoff.")
    slice_start.add_argument("spec", help="Feature slug.")
    slice_start.add_argument("slice", help="Slice name from the plan.")
    slice_start.set_defaults(func=commands["slice_start"])

    slice_verify = slice_subparsers.add_parser("verify", help="Create a slice verification report.")
    slice_verify.add_argument("spec", help="Feature slug.")
    slice_verify.add_argument("slice", help="Slice name from the plan.")
    slice_verify.set_defaults(func=commands["slice_verify"])

    status = subparsers.add_parser("status", help="Show tracked flow state.")
    status.add_argument("spec", nargs="?", help="Optional feature slug.")
    status.add_argument("--json", action="store_true", help="Print the tracked state as JSON.")
    status.set_defaults(func=commands["status"])

    return parser
