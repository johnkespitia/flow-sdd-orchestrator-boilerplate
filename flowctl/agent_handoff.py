from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path
from typing import Callable

from flowctl.evidence import evidence_status_payload, write_evidence_bundle


def _copy_if_exists(*, source: Path, destination_root: Path, rel: Callable[[Path], str]) -> dict[str, object] | None:
    if not source.is_file():
        return None
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / source.name
    shutil.copy2(source, destination)
    return {"source": rel(source), "package_path": rel(destination)}


def agent_handoff_payload(
    *,
    slug: str,
    spec_path: Path,
    plan_path: Path,
    state: dict[str, object],
    report_root: Path,
    evidence_report_root: Path,
    handoff_report_root: Path,
    root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
) -> dict[str, object]:
    evidence = evidence_status_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_path,
        state=state,
        report_root=report_root,
        rel=rel,
        utc_now=utc_now,
    )
    evidence_bundle = write_evidence_bundle(
        payload=evidence,
        evidence_report_root=evidence_report_root,
        root=root,
        rel=rel,
    )
    plan_payload: dict[str, object] = {}
    if plan_path.is_file():
        try:
            parsed = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                plan_payload = parsed
        except json.JSONDecodeError:
            plan_payload = {}
    slices = [item for item in plan_payload.get("slices", []) if isinstance(item, dict)]
    handoff_dir = handoff_report_root / slug
    copied_inputs = [
        item
        for item in (
            _copy_if_exists(source=spec_path, destination_root=handoff_dir, rel=rel),
            _copy_if_exists(source=plan_path, destination_root=handoff_dir, rel=rel),
        )
        if item is not None
    ]
    bundle_info = evidence_bundle.get("bundle", {})
    if isinstance(bundle_info, dict):
        for file_item in bundle_info.get("files", []):
            if not isinstance(file_item, dict):
                continue
            source = root / str(file_item.get("bundle_path", ""))
            copied = _copy_if_exists(source=source, destination_root=handoff_dir / "evidence", rel=rel)
            if copied is not None:
                copied_inputs.append(copied)
    blocked_actions: list[str] = []
    if evidence.get("missing"):
        blocked_actions.extend(str(item) for item in evidence["missing"])
    release_policy = evidence.get("policies", {}).get("release") if isinstance(evidence.get("policies"), dict) else {}
    if isinstance(release_policy, dict):
        blocked_actions.extend(str(item) for item in release_policy.get("blocked_reasons", []))
    next_commands = [
        f"python3 ./flow evidence status {slug} --json",
        f"python3 ./flow policy check {slug} --stage slice-start --json",
        f"python3 ./flow workflow run {slug} --human-gated --json",
    ]
    if not bool(evidence.get("ready_for_release")):
        approval_commands: list[str] = []
        for action in evidence.get("missing", []):
            if action == "spec_approval":
                approval_commands.append(f"python3 ./flow spec approve {slug} --approver <human>")
            if action == "plan_approval":
                approval_commands.append(f"python3 ./flow plan-approve {slug} --approver <human>")
        next_commands = approval_commands + next_commands
    return {
        "feature": slug,
        "generated_at": utc_now(),
        "spec_path": rel(spec_path),
        "plan_path": rel(plan_path),
        "handoff_root": rel(handoff_dir),
        "ready_for_agent": bool(evidence.get("ready_for_release")),
        "blocked_actions": blocked_actions,
        "next_commands": next_commands,
        "execution_contract": {
            "source_of_truth": rel(spec_path),
            "plan": rel(plan_path),
            "evidence_bundle": bundle_info,
            "policy_release_allowed": bool(release_policy.get("allowed")) if isinstance(release_policy, dict) else False,
        },
        "slices": [
            {
                "name": str(item.get("name", "")),
                "repo": str(item.get("repo", "")),
                "branch": str(item.get("branch", "")),
                "worktree": str(item.get("worktree", "")),
                "owned_targets": item.get("owned_targets", []),
                "acceptable_evidence": item.get("acceptable_evidence", []),
                "executor_mode": str(item.get("executor_mode", "")),
                "closeout_rule": str(item.get("closeout_rule", "")),
            }
            for item in slices
        ],
        "evidence": evidence,
        "copied_inputs": copied_inputs,
    }


def write_agent_handoff(
    *,
    payload: dict[str, object],
    handoff_report_root: Path,
    rel: Callable[[Path], str],
) -> dict[str, object]:
    slug = str(payload["feature"])
    handoff_report_root.mkdir(parents=True, exist_ok=True)
    json_path = handoff_report_root / f"{slug}-agent-handoff.json"
    md_path = handoff_report_root / f"{slug}-agent-handoff.md"
    output = dict(payload)
    output["json_report"] = rel(json_path)
    output["markdown_report"] = rel(md_path)
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    commands = "\n".join(f"- `{command}`" for command in output["next_commands"]) or "- none"
    blockers = "\n".join(f"- `{item}`" for item in output["blocked_actions"]) or "- none"
    slices = "\n".join(
        f"- `{item['name']}` repo=`{item['repo']}` executor=`{item['executor_mode']}`"
        for item in output["slices"]
        if isinstance(item, dict)
    ) or "- none"
    md_path.write_text(
        textwrap.dedent(
            f"""\
            # Agent Handoff: {slug}

            - Ready for agent: `{'yes' if output['ready_for_agent'] else 'no'}`
            - Spec: `{output['spec_path']}`
            - Plan: `{output['plan_path']}`
            - Handoff root: `{output['handoff_root']}`

            ## Blockers

            {blockers}

            ## Next commands

            {commands}

            ## Slices

            {slices}
            """
        ),
        encoding="utf-8",
    )
    return output


def command_agent_handoff(
    args,
    *,
    root: Path,
    resolve_spec: Callable[[str], Path],
    spec_slug: Callable[[Path], str],
    plan_root: Path,
    report_root: Path,
    evidence_report_root: Path,
    handoff_report_root: Path,
    read_state: Callable[[str], dict[str, object]],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    spec_path = resolve_spec(args.spec)
    slug = spec_slug(spec_path)
    payload = agent_handoff_payload(
        slug=slug,
        spec_path=spec_path,
        plan_path=plan_root / f"{slug}.json",
        state=read_state(slug),
        report_root=report_root,
        evidence_report_root=evidence_report_root,
        handoff_report_root=handoff_report_root,
        root=root,
        rel=rel,
        utc_now=utc_now,
    )
    output = write_agent_handoff(payload=payload, handoff_report_root=handoff_report_root, rel=rel)
    if bool(getattr(args, "json", False)):
        print(json_dumps(output))
    else:
        print(output["json_report"])
        print(output["markdown_report"])
    return 0 if bool(output["ready_for_agent"]) else 2
