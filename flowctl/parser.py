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

    gateway = subparsers.add_parser("gateway", help="Consume a remote SoftOS gateway from a slave workspace.")
    gateway_subparsers = gateway.add_subparsers(dest="gateway_command", required=True)

    gateway_list = gateway_subparsers.add_parser("list", help="List remote specs from the configured gateway.")
    gateway_list.add_argument("--state", help="Optional state filter.")
    gateway_list.add_argument("--assignee", help="Optional assignee filter.")
    gateway_list.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_list.set_defaults(func=commands["gateway_list"])

    gateway_status = gateway_subparsers.add_parser("status", help="Inspect the local and remote claim state for a spec.")
    gateway_status.add_argument("spec", help="Remote spec id / slug.")
    gateway_status.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_status.set_defaults(func=commands["gateway_status"])

    gateway_current = gateway_subparsers.add_parser("current", help="Alias of `gateway status` for the current claimed spec.")
    gateway_current.add_argument("spec", help="Remote spec id / slug.")
    gateway_current.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_current.set_defaults(func=commands["gateway_status"])

    gateway_claim = gateway_subparsers.add_parser("claim", help="Claim a remote spec for the current actor and fetch it locally.")
    gateway_claim.add_argument("spec", help="Remote spec id / slug.")
    gateway_claim.add_argument("--actor", help="Actor claiming the spec. Defaults to FLOW_ACTOR or USER.")
    gateway_claim.add_argument("--reason", help="Optional audit reason.")
    gateway_claim.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds.")
    gateway_claim.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_claim.set_defaults(func=commands["gateway_claim"])

    gateway_fetch = gateway_subparsers.add_parser("fetch-spec", help="Fetch the canonical remote spec markdown into the local workspace.")
    gateway_fetch.add_argument("spec", help="Remote spec id / slug.")
    gateway_fetch.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_fetch.set_defaults(func=commands["gateway_fetch_spec"])

    gateway_heartbeat = gateway_subparsers.add_parser("heartbeat", help="Renew the remote lock for a claimed spec.")
    gateway_heartbeat.add_argument("spec", help="Remote spec id / slug.")
    gateway_heartbeat.add_argument("--reason", help="Optional audit reason.")
    gateway_heartbeat.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds.")
    gateway_heartbeat.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_heartbeat.set_defaults(func=commands["gateway_heartbeat"])

    gateway_transition = gateway_subparsers.add_parser("transition", help="Publish a state transition for a remotely claimed spec.")
    gateway_transition.add_argument("spec", help="Remote spec id / slug.")
    gateway_transition.add_argument("to_state", help="Target state in the gateway registry.")
    gateway_transition.add_argument("--reason", help="Optional audit reason.")
    gateway_transition.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_transition.set_defaults(func=commands["gateway_transition"])

    gateway_release = gateway_subparsers.add_parser("release", help="Release the remote lock for a claimed spec.")
    gateway_release.add_argument("spec", help="Remote spec id / slug.")
    gateway_release.add_argument("--reason", help="Optional audit reason.")
    gateway_release.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_release.set_defaults(func=commands["gateway_release"])

    gateway_reassign = gateway_subparsers.add_parser("reassign", help="Reassign a remotely claimed spec to another actor.")
    gateway_reassign.add_argument("spec", help="Remote spec id / slug.")
    gateway_reassign.add_argument("to_actor", help="Target actor for the reassignment.")
    gateway_reassign.add_argument("--role", default="assignee", help="Operational role for reassignment: assignee, coordinator or admin.")
    gateway_reassign.add_argument("--force", action="store_true", help="Force reassignment. Only valid for admin role.")
    gateway_reassign.add_argument("--reason", help="Optional audit reason.")
    gateway_reassign.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds for the new assignee.")
    gateway_reassign.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_reassign.set_defaults(func=commands["gateway_reassign"])

    gateway_pick = gateway_subparsers.add_parser("pick", help="Pick the first eligible remote spec using a stable assisted-selection policy.")
    gateway_pick.add_argument("--actor", help="Actor claiming the picked spec. Defaults to FLOW_ACTOR or USER.")
    gateway_pick.add_argument("--state", dest="states", action="append", help="Eligible remote state filter. Repeatable; default is `new` and `triaged`.")
    gateway_pick.add_argument("--reason", help="Optional audit reason.")
    gateway_pick.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds.")
    gateway_pick.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_pick.set_defaults(func=commands["gateway_pick"])

    gateway_poll = gateway_subparsers.add_parser("poll", help="Run one autonomous polling attempt against the remote gateway.")
    gateway_poll.add_argument("--actor", help="Actor claiming the picked spec. Defaults to FLOW_ACTOR or USER.")
    gateway_poll.add_argument("--state", dest="states", action="append", help="Eligible remote state filter. Repeatable; default is `new` and `triaged`.")
    gateway_poll.add_argument("--reason", help="Optional audit reason.")
    gateway_poll.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds.")
    gateway_poll_auto_plan = gateway_poll.add_mutually_exclusive_group()
    gateway_poll_auto_plan.add_argument(
        "--auto-plan",
        dest="auto_plan",
        action="store_true",
        default=None,
        help="Enable the opt-in `claim -> plan` gate for this invocation.",
    )
    gateway_poll_auto_plan.add_argument(
        "--no-auto-plan",
        dest="auto_plan",
        action="store_false",
        help="Disable the `claim -> plan` gate for this invocation even if the workspace enables it.",
    )
    gateway_poll.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_poll.set_defaults(func=commands["gateway_poll"])

    gateway_watch = gateway_subparsers.add_parser("watch", help="Run a bounded polling loop until a spec is claimed or the declared limits are reached.")
    gateway_watch.add_argument("--actor", help="Actor claiming the picked spec. Defaults to FLOW_ACTOR or USER.")
    gateway_watch.add_argument("--state", dest="states", action="append", help="Eligible remote state filter. Repeatable; default is `new` and `triaged`.")
    gateway_watch.add_argument("--reason", help="Optional audit reason.")
    gateway_watch.add_argument("--ttl-seconds", type=int, default=120, help="Lock TTL in seconds.")
    gateway_watch.add_argument("--interval-seconds", type=float, default=15, help="Base interval between polling attempts.")
    gateway_watch.add_argument("--max-interval-seconds", type=float, default=60, help="Maximum interval after backoff.")
    gateway_watch.add_argument("--backoff-multiplier", type=float, default=1.5, help="Backoff multiplier applied after each empty attempt.")
    gateway_watch.add_argument("--timeout-seconds", type=float, default=600, help="Maximum wall-clock time for the watch loop.")
    gateway_watch.add_argument("--max-attempts", type=int, default=40, help="Maximum polling attempts before stopping.")
    gateway_watch_auto_plan = gateway_watch.add_mutually_exclusive_group()
    gateway_watch_auto_plan.add_argument(
        "--auto-plan",
        dest="auto_plan",
        action="store_true",
        default=None,
        help="Enable the opt-in `claim -> plan` gate for this invocation.",
    )
    gateway_watch_auto_plan.add_argument(
        "--no-auto-plan",
        dest="auto_plan",
        action="store_false",
        help="Disable the `claim -> plan` gate for this invocation even if the workspace enables it.",
    )
    gateway_watch.add_argument("--json", action="store_true", help="Print the result as JSON.")
    gateway_watch.set_defaults(func=commands["gateway_watch"])

    memory = subparsers.add_parser("memory", help="Operate optional agent memory through Engram.")
    memory_subparsers = memory.add_subparsers(dest="memory_command", required=True)

    memory_doctor = memory_subparsers.add_parser("doctor", help="Inspect Engram availability and project-scoped storage.")
    memory_doctor.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_doctor.set_defaults(func=commands["memory_doctor"])

    memory_smoke = memory_subparsers.add_parser("smoke", help="Run a non-blocking Engram install and storage smoke.")
    memory_smoke.add_argument("--save", action="store_true", help="Also write a small smoke memory to the project database.")
    memory_smoke.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_smoke.set_defaults(func=commands["memory_smoke"])

    memory_stats = memory_subparsers.add_parser("stats", help="Show Engram memory stats for the project-scoped database.")
    memory_stats.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_stats.set_defaults(func=commands["memory_stats"])

    memory_search = memory_subparsers.add_parser("search", help="Search project-scoped Engram memories.")
    memory_search.add_argument("query", help="Search query.")
    memory_search.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_search.set_defaults(func=commands["memory_search"])

    memory_export = memory_subparsers.add_parser("export", help="Export Engram search results as structured JSON.")
    memory_export.add_argument("--output", help="Output JSON path. Defaults to .flow/memory/exports/<project>-<timestamp>.json.")
    memory_export.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_export.set_defaults(func=commands["memory_export"])

    memory_backup = memory_subparsers.add_parser("backup", help="Create a timestamped native Engram export under .flow/memory/backups.")
    memory_backup.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_backup.set_defaults(func=commands["memory_backup"])

    memory_import = memory_subparsers.add_parser("import", help="Validate or import a native Engram export JSON file.")
    memory_import.add_argument("file", help="Engram export JSON file to import.")
    memory_import.add_argument("--confirm", action="store_true", help="Execute `engram import`. Without this flag the command is a dry-run.")
    memory_import.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_import.set_defaults(func=commands["memory_import"])

    memory_prune = memory_subparsers.add_parser("prune", help="Generate a non-destructive advisory prune report.")
    memory_prune.add_argument("--query", help="Mark memories matching a query as prune candidates.")
    memory_prune.add_argument("--older-than-days", type=int, help="Mark memories at least this old as prune candidates.")
    memory_prune.add_argument("--keep-latest", type=int, help="Mark all but the latest N memories as prune candidates.")
    memory_prune.add_argument("--output", help="Output report path. Defaults to .flow/memory/prune/<project>-<timestamp>-report.json.")
    memory_prune.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_prune.set_defaults(func=commands["memory_prune"])

    memory_save = memory_subparsers.add_parser("save", help="Save an explicit consultive memory.")
    memory_save.add_argument("title", help="Short memory title.")
    memory_save_body = memory_save.add_mutually_exclusive_group(required=True)
    memory_save_body.add_argument("--body", help="Memory body. Do not include secrets or sensitive data.")
    memory_save_body.add_argument("--body-file", help="Path to a UTF-8 file containing the memory body.")
    memory_save.add_argument("--json", action="store_true", help="Print the result as JSON.")
    memory_save.set_defaults(func=commands["memory_save"])

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

    workspace = subparsers.add_parser("workspace", help="Run commands through the canonical workspace devcontainer.")
    workspace_subparsers = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_exec = workspace_subparsers.add_parser(
        "exec",
        help="Execute a command in the workspace service, or locally when already inside the devcontainer.",
    )
    workspace_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute after `--`.")
    workspace_exec.set_defaults(func=commands["workspace_exec"])

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

    workflow = subparsers.add_parser("workflow", help="Run the BMAD-first, Tessl-backed orchestration layer.")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)

    def add_workflow_orchestrator_args(parser):
        parser.add_argument(
            "--orchestrator",
            choices=["bmad"],
            help="Override workflow orchestrator for this command (default from workspace config/env).",
        )
        parser.add_argument(
            "--force-orchestrator",
            action="store_true",
            help="Fail if the selected orchestrator is not BMAD.",
        )

    workflow_doctor = workflow_subparsers.add_parser("doctor", help="Validate that BMAD and Tessl are ready as the default orchestration layer.")
    add_workflow_orchestrator_args(workflow_doctor)
    workflow_doctor.add_argument("--json", action="store_true", help="Print the workflow doctor payload as JSON.")
    workflow_doctor.set_defaults(func=commands["workflow_doctor"])

    workflow_intake = workflow_subparsers.add_parser("intake", help="Create a draft spec plus orchestration handoff anchored in BMAD and Tessl.")
    workflow_intake.add_argument("slug", help="Stable feature slug.")
    workflow_intake.add_argument("--title", required=True, help="Human title for the feature spec.")
    workflow_intake.add_argument("--repo", action="append", help="Repo id or alias (`root`) from `workspace.config.json`. Repeatable.")
    workflow_intake.add_argument("--runtime", action="append", choices=available_runtime_names(root), help="Required project runtime. Repeatable.")
    workflow_intake.add_argument("--service", action="append", choices=available_service_runtime_names(root), help="Required service runtime. Repeatable.")
    workflow_intake.add_argument("--capability", action="append", choices=available_capability_names(root), help="Required workspace capability. Repeatable.")
    workflow_intake.add_argument("--depends-on", action="append", help="Required upstream spec slug. Repeatable.")
    workflow_intake.add_argument("--description", help="Optional intake context used to prefill the spec body.")
    workflow_intake.add_argument("--acceptance-criteria", action="append", help="Acceptance criteria line. Repeatable.")
    add_workflow_orchestrator_args(workflow_intake)
    workflow_intake.add_argument("--json", action="store_true", help="Print the intake bundle as JSON.")
    workflow_intake.set_defaults(func=commands["workflow_intake"])

    workflow_next = workflow_subparsers.add_parser("next-step", help="Summarize the next orchestrated step for a feature.")
    workflow_next.add_argument("spec", help="Spec slug or path.")
    add_workflow_orchestrator_args(workflow_next)
    workflow_next.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    workflow_next.set_defaults(func=commands["workflow_next_step"])

    workflow_close = workflow_subparsers.add_parser("close-feature", help="Consolidate verified slices and emit a final closeout report.")
    workflow_close.add_argument("spec", help="Spec slug or path.")
    workflow_close.add_argument("--json", action="store_true", help="Print the closeout payload as JSON.")
    workflow_close.set_defaults(func=commands["workflow_close_feature"])

    workflow_execute = workflow_subparsers.add_parser("execute-feature", help="Prepare an approved feature for executor subagents.")
    workflow_execute.add_argument("spec", help="Spec slug or path.")
    workflow_execute.add_argument("--refresh-plan", action="store_true", help="Regenerate the flow plan before producing handoffs.")
    workflow_execute.add_argument("--start-slices", action="store_true", help="Materialize worktrees and handoffs for every planned slice.")
    workflow_execute.add_argument("--no-worktree-cleanup", action="store_true", help="Skip automatic stale worktree cleanup after preparing the execution bundle.")
    add_workflow_orchestrator_args(workflow_execute)
    workflow_execute.add_argument("--json", action="store_true", help="Print the execution bundle as JSON.")
    workflow_execute.set_defaults(func=commands["workflow_execute_feature"])

    workflow_run = workflow_subparsers.add_parser("run", help="Execute the autonomous SDLC stage engine for a feature.")
    workflow_run.add_argument("spec", help="Spec slug or path.")
    workflow_run.add_argument("--pause-at-stage", help="Pause before executing the given stage.")
    workflow_run.add_argument("--resume-from-stage", help="Resume execution from the given stage.")
    workflow_run.add_argument("--retry-stage", help="Retry a specific failed stage and continue.")
    workflow_run.add_argument("--human-gated", action="store_true", help="Pause instead of executing when central policy requires human approval.")
    add_workflow_orchestrator_args(workflow_run)
    workflow_run.add_argument("--json", action="store_true", help="Print the engine result as JSON.")
    workflow_run.set_defaults(func=commands["workflow_run"])

    workflow_pause = workflow_subparsers.add_parser("pause", help="Pause workflow engine at a specific stage.")
    workflow_pause.add_argument("spec", help="Spec slug or path.")
    workflow_pause.add_argument("--stage", required=True, help="Stage name where the engine should pause.")
    workflow_pause.add_argument("--json", action="store_true", help="Print the pause result as JSON.")
    workflow_pause.set_defaults(func=commands["workflow_pause"])

    workflow_resume = workflow_subparsers.add_parser("resume", help="Resume a paused workflow engine.")
    workflow_resume.add_argument("spec", help="Spec slug or path.")
    workflow_resume.add_argument("--stage", help="Optional stage name to resume from.")
    add_workflow_orchestrator_args(workflow_resume)
    workflow_resume.add_argument("--json", action="store_true", help="Print the resume result as JSON.")
    workflow_resume.set_defaults(func=commands["workflow_resume"])

    workflow_retry = workflow_subparsers.add_parser("retry", help="Retry a failed stage and continue engine execution.")
    workflow_retry.add_argument("spec", help="Spec slug or path.")
    workflow_retry.add_argument("--stage", required=True, help="Failed stage to retry.")
    add_workflow_orchestrator_args(workflow_retry)
    workflow_retry.add_argument("--json", action="store_true", help="Print the retry result as JSON.")
    workflow_retry.set_defaults(func=commands["workflow_retry"])

    skills = subparsers.add_parser("skills", help="Manage assistant skills through a versioned workspace manifest.")
    skills_subparsers = skills.add_subparsers(dest="skills_command", required=True)
    for name, help_text in [
        ("doctor", "Validate `workspace.skills.json` and skill runtimes."),
        ("list", "List skill entries from `workspace.skills.json`."),
    ]:
        parser_item = skills_subparsers.add_parser(name, help=help_text)
        parser_item.add_argument("--json", action="store_true", help="Print the result as JSON.")
        parser_item.set_defaults(func=commands[f"skills_{name}"])

    skills_context = skills_subparsers.add_parser(
        "context",
        help="Resolve runtime and agent_skill_refs for a repo or for repos affected by a spec.",
    )
    skills_context.add_argument("--json", action="store_true", help="Print the result as JSON.")
    skills_context.add_argument("--repo", help="Repo id from workspace.config.json.")
    skills_context.add_argument("--spec", help="Spec slug or path; resolves repos from targets.")
    skills_context.set_defaults(func=commands["skills_context"])

    skills_discover = skills_subparsers.add_parser(
        "discover",
        help="Search for skills in tessl.io and skills.sh by term (via Skyll API).",
    )
    skills_discover.add_argument("query", nargs="?", default="", help="Search term (e.g. golang, react, testing).")
    skills_discover.add_argument("--limit", type=int, default=10, help="Max results (1-50, default 10).")
    skills_discover.add_argument("--json", action="store_true", help="Print the result as JSON.")
    skills_discover.set_defaults(func=commands["skills_discover"])

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

    skills_install = skills_subparsers.add_parser(
        "install",
        help="Resolve and register a skill from Tessl or skills.sh, and optionally attach it to a runtime.",
    )
    skills_install.add_argument(
        "identifier",
        help="Skill identifier or source. Tessl se resuelve primero; skills.sh despues.",
    )
    skills_install.add_argument(
        "--name",
        help="Optional manifest entry name. Defaults to the identifier.",
    )
    skills_install.add_argument(
        "--provider",
        help="Optional provider hint: `tessl` or `skills-sh`. Required when the identifier matches both.",
    )
    skills_install.add_argument(
        "--runtime",
        choices=available_runtime_names(root),
        help="Optional runtime pack id whose `agent_skill_refs` will be updated.",
    )
    skills_install.set_defaults(func=commands["skills_install"])

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
    worktree_list = worktree_subparsers.add_parser(
        "list",
        help="List worktrees under `.worktrees/` and classify active vs cleanable entries.",
    )
    worktree_list.add_argument("--name", action="append", help="Filter by exact worktree directory name. Repeatable.")
    worktree_list.add_argument("--feature", action="append", help="Filter by feature/spec slug. Repeatable.")
    worktree_list.add_argument("--stale-only", action="store_true", help="Show only cleanable stale worktrees.")
    worktree_list.add_argument("--json", action="store_true", help="Print the inventory as JSON.")
    worktree_list.set_defaults(func=commands["worktree_list"])
    worktree_clean = worktree_subparsers.add_parser(
        "clean",
        help="Remove stale worktrees safely and prune orphan metadata.",
    )
    worktree_clean.add_argument("name", nargs="?", help="Optional exact worktree directory name under `.worktrees/`.")
    worktree_clean.add_argument("--feature", action="append", help="Clean worktrees associated with a feature/spec slug. Repeatable.")
    worktree_clean.add_argument("--stale", action="store_true", help="Clean only orphan or closed clean worktrees. Default when no selector is provided.")
    worktree_clean.add_argument("--force", action="store_true", help="Allow removing dirty or still-active worktrees.")
    worktree_clean.add_argument("--dry-run", action="store_true", help="Preview cleanup actions without mutating git worktrees.")
    worktree_clean.add_argument("--json", action="store_true", help="Print the cleanup report as JSON.")
    worktree_clean.set_defaults(func=commands["worktree_clean"])

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
    ci_integration.add_argument(
        "--bootstrap-runtime",
        action="store_true",
        help="Opt-in: ejecuta composer/pnpm install dentro del servicio antes del preflight (entorno Compose).",
    )
    ci_integration.add_argument(
        "--preflight-relaxed",
        action="store_true",
        help="Desactiva preflight estricto incluso en perfil smoke:ci-clean (solo diagnostico / bypass controlado).",
    )
    ci_integration.add_argument("--json", action="store_true", help="Print the integration report as JSON.")
    ci_integration.set_defaults(func=commands["ci_integration"])

    policy = subparsers.add_parser("policy", help="Run central SoftOS policy checks for sensitive stages.")
    policy_subparsers = policy.add_subparsers(dest="policy_command", required=True)
    policy_check = policy_subparsers.add_parser("check", help="Check whether a spec may enter a sensitive stage.")
    policy_check.add_argument("spec", help="Spec path or slug.")
    policy_check.add_argument(
        "--stage",
        required=True,
        choices=["plan", "slice-start", "workflow-run", "release"],
        help="Sensitive stage to evaluate.",
    )
    policy_check.add_argument("--json", action="store_true", help="Print the policy decision as JSON.")
    policy_check.set_defaults(func=commands["policy_check"])

    release = subparsers.add_parser("release", help="Manage release manifests, promotions and post-release verification.")
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
    release_promote.add_argument(
        "--deploy-repo",
        help="Optional repo id used to resolve deploy provider from `workspace.config.json`.",
    )
    release_promote.add_argument("--approver", help="Required for staging and production promotions.")
    release_promote.add_argument("--skip-verify", action="store_true", help="Skip post-release verification after promote.")
    release_promote.add_argument(
        "--require-pipelines",
        action="store_true",
        help="Fail if pipeline checks are unavailable or missing during post-release verification.",
    )
    release_promote.add_argument("--no-worktree-cleanup", action="store_true", help="Skip automatic stale worktree cleanup after a successful promote.")
    release_promote.add_argument("--json", action="store_true", help="Print the promotion result as JSON.")
    release_promote.set_defaults(func=commands["release_promote"])

    release_verify = release_subparsers.add_parser("verify", help="Verify release repos and pipeline checks for an environment.")
    release_verify.add_argument("--version", required=True, help="Release version.")
    release_verify.add_argument("--env", dest="environment", required=True, choices=["preview", "staging", "production"])
    release_verify.add_argument(
        "--require-pipelines",
        action="store_true",
        help="Fail if pipeline checks are unavailable or missing.",
    )
    release_verify.add_argument("--json", action="store_true", help="Print the verification result as JSON.")
    release_verify.set_defaults(func=commands["release_verify"])

    release_publish = release_subparsers.add_parser(
        "publish",
        help="Create a semver OSS release: update changelog, tag, push and optionally publish GitHub Release notes.",
    )
    release_publish.add_argument(
        "--bump",
        choices=["auto", "patch", "minor", "major"],
        default="auto",
        help="Semver bump. `auto` infers from conventional commits since the last semver tag.",
    )
    release_publish.add_argument(
        "--version",
        help="Explicit semver tag (for example `v0.1.3`). Overrides automatic version calculation.",
    )
    release_publish.add_argument(
        "--since-tag",
        help="Optional starting semver tag. Defaults to the latest semver tag found in git.",
    )
    release_publish.add_argument(
        "--skip-github",
        action="store_true",
        help="Skip `gh release create` and only update changelog + git tag.",
    )
    release_publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview version, notes and changelog content without mutating git or files.",
    )
    release_publish.add_argument(
        "--memory-save-outcome",
        dest="memory_save_outcome",
        action="store_true",
        default=None,
        help="After a successful publish, save a consultive Engram release outcome memory.",
    )
    release_publish.add_argument(
        "--no-memory-save-outcome",
        dest="memory_save_outcome",
        action="store_false",
        help="Disable release outcome memory even if workspace config enables it.",
    )
    release_publish.add_argument("--no-worktree-cleanup", action="store_true", help="Skip automatic stale worktree cleanup after a successful publish.")
    release_publish.add_argument("--json", action="store_true", help="Print the publish plan/result as JSON.")
    release_publish.set_defaults(func=commands["release_publish"])

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
    add_project.add_argument("--capabilities", help="Optional framework capabilities (comma-separated). e.g. nextjs,typescript")
    add_project.add_argument("--service-name", help="Compose service name. Defaults to the project id.")
    add_project.add_argument("--port", type=int, help="Optional port to expose for the new compose service.")
    add_project.add_argument("--no-compose", action="store_true", help="Skip compose service scaffolding even if the runtime provides a template.")
    add_project.add_argument("--use-existing-dir", action="store_true", help="Allow registering an existing non-empty directory instead of requiring a fresh placeholder.")
    add_project.add_argument("--submodule-url", help="Git URL to create the project path as a submodule and register it automatically.")
    add_project.add_argument("--submodule-branch", help="Optional branch passed to `git submodule add -b` (requires --submodule-url).")
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

    repo = subparsers.add_parser("repo", help="Run commands against a repo using its canonical compose service/workdir.")
    repo_subparsers = repo.add_subparsers(dest="repo_command", required=True)
    repo_exec = repo_subparsers.add_parser(
        "exec",
        help="Execute a command in the repo service, or locally when already inside the devcontainer.",
    )
    repo_exec.add_argument("repo", choices=repo_names, help="Repo id from `workspace.config.json`.")
    repo_exec.add_argument(
        "--workdir",
        help="Optional host/workspace path to execute from. Use this for slice worktrees to avoid mixing the base checkout with the worktree under test.",
    )
    repo_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute after `--`.")
    repo_exec.set_defaults(func=commands["repo_exec"])

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
    spec_create.add_argument("--description", help="Optional context used to prefill the generated spec.")
    spec_create.add_argument("--acceptance-criteria", action="append", help="Acceptance criteria line. Repeatable.")
    spec_create.set_defaults(func=commands["spec_create"])

    spec_review = spec_subparsers.add_parser("review", help="Create a spec review report.")
    spec_review.add_argument("spec", help="Spec path or slug.")
    spec_review.add_argument("--json", action="store_true", help="Print a structured review result.")
    spec_review.set_defaults(func=commands["spec_review"])

    spec_guard = spec_subparsers.add_parser("guard", help="Fail fast when stable surfaces change without a governing spec.")
    spec_guard.add_argument("spec", nargs="?", help="Optional spec path or slug.")
    spec_guard.add_argument("--all", action="store_true", help="Check every spec under `specs/**`.")
    spec_guard.add_argument("--changed", action="store_true", help="Check changed specs in git diff.")
    spec_guard.add_argument("--staged", action="store_true", help="Check staged changes before commit.")
    spec_guard.add_argument("--base", help="Base git ref for `--changed`.")
    spec_guard.add_argument("--head", help="Head git ref for `--changed`.")
    spec_guard.add_argument("--json", action="store_true", help="Print the guard report as JSON.")
    spec_guard.set_defaults(func=commands["spec_guard"])

    spec_approve = spec_subparsers.add_parser("approve", help="Approve a canonical spec.")
    spec_approve.add_argument("spec", help="Spec path or slug.")
    spec_approve.add_argument("--approver", help="Identity recorded for the approval. Defaults to FLOW_APPROVER/USER.")
    spec_approve.set_defaults(func=commands["spec_approve"])

    spec_approval_status = spec_subparsers.add_parser("approval-status", help="Inspect the formal approval gate for a spec.")
    spec_approval_status.add_argument("spec", help="Spec path or slug.")
    spec_approval_status.add_argument("--json", action="store_true", help="Print approval status as JSON.")
    spec_approval_status.set_defaults(func=commands["spec_approval_status"])

    spec_generate_contracts = spec_subparsers.add_parser("generate-contracts", help="Generate derived contract artifacts from `json contract` blocks in a spec.")
    spec_generate_contracts.add_argument("spec", help="Spec path or slug.")
    spec_generate_contracts.add_argument("--json", action="store_true", help="Print generated artifacts as JSON.")
    spec_generate_contracts.set_defaults(func=commands["spec_generate_contracts"])

    plan = subparsers.add_parser("plan", help="Create a default worktree plan from a spec.")
    plan.add_argument("spec", help="Spec path or slug.")
    plan.add_argument(
        "--memory-recall",
        dest="memory_recall",
        action="store_true",
        default=None,
        help="Before planning, write a consultive Engram recall report for this spec.",
    )
    plan.add_argument(
        "--no-memory-recall",
        dest="memory_recall",
        action="store_false",
        help="Disable plan recall even if workspace config enables it.",
    )
    plan.set_defaults(func=commands["plan"])

    plan_approve = subparsers.add_parser("plan-approve", help="Approve the current generated plan for a spec.")
    plan_approve.add_argument("spec", help="Spec path or slug.")
    plan_approve.add_argument("--approver", help="Identity recorded for the approval. Defaults to FLOW_APPROVER/USER.")
    plan_approve.set_defaults(func=commands["plan_approve"])

    plan_approval_status = subparsers.add_parser("plan-approval-status", help="Inspect the formal approval gate for a generated plan.")
    plan_approval_status.add_argument("spec", help="Spec path or slug.")
    plan_approval_status.add_argument("--json", action="store_true", help="Print plan approval status as JSON.")
    plan_approval_status.set_defaults(func=commands["plan_approval_status"])

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

    evidence = subparsers.add_parser("evidence", help="Inspect and bundle evidence for a spec.")
    evidence_subparsers = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_status = evidence_subparsers.add_parser("status", help="Summarize release readiness evidence for a spec.")
    evidence_status.add_argument("spec", help="Spec path or slug.")
    evidence_status.add_argument("--json", action="store_true", help="Print evidence status as JSON.")
    evidence_status.set_defaults(func=commands["evidence_status"])
    evidence_bundle = evidence_subparsers.add_parser("bundle", help="Write an evidence bundle under .flow/reports/evidence.")
    evidence_bundle.add_argument("spec", help="Spec path or slug.")
    evidence_bundle.add_argument("--json", action="store_true", help="Print evidence bundle as JSON.")
    evidence_bundle.set_defaults(func=commands["evidence_bundle"])

    ops = subparsers.add_parser("ops", help="Operational observability commands (metrics, dashboards).")
    ops_subparsers = ops.add_subparsers(dest="ops_command", required=True)
    ops_metrics = ops_subparsers.add_parser("metrics", help="Print aggregated workflow metrics (throughput, failure_rate, latency, retries, DLQ).")
    ops_metrics.add_argument("--json", action="store_true", help="Print metrics as JSON.")
    ops_metrics.set_defaults(func=commands["ops_metrics"])
    ops_dashboard = ops_subparsers.add_parser("dashboard", help="Print a runs dashboard with engine status and stages.")
    ops_dashboard.add_argument("--spec", help="Filter runs by spec slug fragment.")
    ops_dashboard.add_argument("--repo", help="Filter runs by repo fragment.")
    ops_dashboard.add_argument("--actor", help="Filter runs by actor fragment.")
    ops_dashboard.add_argument("--status", help="Filter runs by engine status fragment.")
    ops_dashboard.add_argument("--json", action="store_true", help="Print dashboard as JSON.")
    ops_dashboard.set_defaults(func=commands["ops_dashboard"])

    ops_sla = ops_subparsers.add_parser("sla", help="Evaluate SLA thresholds by stage and persist alerts.")
    ops_sla.add_argument("--json", action="store_true", help="Print SLA alerts as JSON.")
    ops_sla.set_defaults(func=commands["ops_sla"])

    decision = ops_subparsers.add_parser("decision-log", help="Record and inspect agent/human operational decisions.")
    decision_subparsers = decision.add_subparsers(dest="decision_command", required=True)
    decision_add = decision_subparsers.add_parser("add", help="Append a decision entry to the operations log.")
    decision_add.add_argument("--actor-type", required=True, choices=["agent", "human"], help="Actor type.")
    decision_add.add_argument("--actor", required=True, help="Actor id or name.")
    decision_add.add_argument("--decision", required=True, help="Decision summary.")
    decision_add.add_argument("--context", required=True, help="Context for the decision.")
    decision_add.add_argument("--impact-or-risk", required=True, help="Impact or risk assessment.")
    decision_add.add_argument("--json", action="store_true", help="Print the appended entry as JSON.")
    decision_add.set_defaults(func=commands["ops_decision_add"])

    decision_list = decision_subparsers.add_parser("list", help="List recent decision log entries.")
    decision_list.add_argument("--limit", type=int, default=100, help="Max entries to return.")
    decision_list.add_argument("--json", action="store_true", help="Print the decision log as JSON.")
    decision_list.set_defaults(func=commands["ops_decision_list"])

    # `serve-metrics` era un servidor HTTP ligero embebido en `flow`. La responsabilidad
    # de exponer `/metrics` vive ahora en `gateway`, por lo que este subcomando se
    # elimina de la CLI para evitar duplicar endpoints.

    return parser
