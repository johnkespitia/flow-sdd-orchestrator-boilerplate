from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowctl import release


def test_release_promote_passes_softos_github_token_to_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_env: dict[str, str] = {}
    manifest_path = tmp_path / "releases" / "manifests" / "v1.2.3.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"version": "v1.2.3", "features": [], "repos": {}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("SOFTOS_GITHUB_TOKEN", "softos-token-123")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    args = argparse.Namespace(
        version="v1.2.3",
        environment="staging",
        approver="release-manager",
        provider=None,
        deploy_repo=None,
        skip_verify=True,
        require_pipelines=False,
        json=True,
    )

    rc = release.command_release_promote(
        args,
        load_release_manifest=lambda _version: dict(manifest),
        workspace_config={"repos": {}},
        root_repo="sdd-workspace-boilerplate",
        load_providers_config=lambda: {"release": {"providers": {"github-actions": {"entrypoint": "scripts/providers/release/github_actions.sh"}}}},
        select_provider=lambda payload, category, explicit=None: ("github-actions", {"entrypoint": "scripts/providers/release/github_actions.sh"}),
        provider_entrypoint_path=lambda config: tmp_path / "scripts" / "providers" / "release" / "github_actions.sh",
        run_provider=lambda category, action, provider_name, config, env: captured_env.update(env) or {
            "provider": provider_name,
            "entrypoint": "scripts/providers/release/github_actions.sh",
            "returncode": 0,
            "output_tail": "",
        },
        release_manifest_path=lambda version: manifest_path,
        release_promotion_path=lambda version, environment: tmp_path / f"{version}-{environment}.json",
        release_verification_path=lambda version, environment: tmp_path / f"{version}-{environment}-verification.json",
        root=tmp_path,
        rel=lambda path: str(path),
        utc_now=lambda: "2026-04-03T00:00:00+00:00",
        write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        read_state=lambda slug: {},
        write_state=lambda slug, payload: None,
        replace_frontmatter_status=lambda path, status: None,
        json_dumps=lambda payload: json.dumps(payload),
    )

    assert rc == 0
    assert captured_env["SOFTOS_GITHUB_TOKEN"] == "softos-token-123"
    assert captured_env["GH_TOKEN"] == "softos-token-123"
    assert captured_env["GITHUB_TOKEN"] == "softos-token-123"


def test_release_promote_fails_when_pr_provider_cannot_resolve_source_ref(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "releases" / "manifests" / "v1.2.3.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "v1.2.3",
        "features": [],
        "repos": {
            "legacy-api": {
                "path": str(tmp_path / "legacy-api"),
                "sha": "abc123",
                "remote_ref_candidates": ["origin/main", "origin/release"],
                "release_ref": None,
            }
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    args = argparse.Namespace(
        version="v1.2.3",
        environment="staging",
        approver="release-manager",
        provider=None,
        deploy_repo="legacy-api",
        skip_verify=False,
        require_pipelines=False,
        json=True,
    )

    try:
        release.command_release_promote(
            args,
            load_release_manifest=lambda _version: dict(manifest),
            workspace_config={
                "repos": {
                    "legacy-api": {
                        "deploy": {
                            "provider": "github-actions",
                            "promotion_strategy": {"mode": "pull_request"},
                            "contract": {
                                "deploy_requires_pr": True,
                                "deploy_requires_healthcheck": True,
                                "post_deploy_smoke_required": False,
                            },
                            "verify": {"mode": "healthcheck", "retry": {"attempts": 3}},
                            "env": {
                                "FLOW_DEPLOY_GITHUB_REPO": "acme/legacy-api",
                                "FLOW_DEPLOY_GITHUB_REF": "staging",
                            },
                        }
                    }
                }
            },
            root_repo="sdd-workspace-boilerplate",
            load_providers_config=lambda: {"release": {"providers": {"github-actions": {"entrypoint": "scripts/providers/release/github_actions.sh", "contract": {"requires_source_ref": True, "requires_target_ref": True, "supports_pr_promotion": True, "requires_post_deploy_verify": True, "verify_mode": "healthcheck"}}}}},
            select_provider=lambda payload, category, explicit=None: (
                "github-actions",
                {
                    "entrypoint": "scripts/providers/release/github_actions.sh",
                    "contract": {
                        "requires_source_ref": True,
                        "requires_target_ref": True,
                        "supports_pr_promotion": True,
                        "requires_post_deploy_verify": True,
                        "verify_mode": "healthcheck",
                    },
                },
            ),
            provider_entrypoint_path=lambda config: tmp_path / "scripts" / "providers" / "release" / "github_actions.sh",
            run_provider=lambda category, action, provider_name, config, env: {
                "provider": provider_name,
                "entrypoint": "scripts/providers/release/github_actions.sh",
                "returncode": 0,
                "output_tail": "",
            },
            release_manifest_path=lambda version: manifest_path,
            release_promotion_path=lambda version, environment: tmp_path / f"{version}-{environment}.json",
            release_verification_path=lambda version, environment: tmp_path / f"{version}-{environment}-verification.json",
            root=tmp_path,
            rel=lambda path: str(path),
            utc_now=lambda: "2026-04-03T00:00:00+00:00",
            write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
            read_state=lambda slug: {},
            write_state=lambda slug, payload: None,
            replace_frontmatter_status=lambda path, status: None,
            json_dumps=lambda payload: json.dumps(payload),
        )
    except SystemExit as exc:
        assert "source_ref" in str(exc)
    else:
        raise AssertionError("release promote deberia fallar si no puede derivar source_ref.")


def test_release_promote_fails_when_skip_verify_breaks_provider_contract(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "releases" / "manifests" / "v1.2.3.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"version": "v1.2.3", "features": [], "repos": {}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    args = argparse.Namespace(
        version="v1.2.3",
        environment="staging",
        approver="release-manager",
        provider="github-actions",
        deploy_repo=None,
        skip_verify=True,
        require_pipelines=False,
        json=True,
    )

    try:
        release.command_release_promote(
            args,
            load_release_manifest=lambda _version: dict(manifest),
            workspace_config={"repos": {}},
            root_repo="sdd-workspace-boilerplate",
            load_providers_config=lambda: {"release": {"providers": {"github-actions": {"entrypoint": "scripts/providers/release/github_actions.sh", "contract": {"requires_post_deploy_verify": True}}}}},
            select_provider=lambda payload, category, explicit=None: (
                "github-actions",
                {
                    "entrypoint": "scripts/providers/release/github_actions.sh",
                    "contract": {
                        "requires_post_deploy_verify": True,
                    },
                },
            ),
            provider_entrypoint_path=lambda config: tmp_path / "scripts" / "providers" / "release" / "github_actions.sh",
            run_provider=lambda category, action, provider_name, config, env: {
                "provider": provider_name,
                "entrypoint": "scripts/providers/release/github_actions.sh",
                "returncode": 0,
                "output_tail": "",
            },
            release_manifest_path=lambda version: manifest_path,
            release_promotion_path=lambda version, environment: tmp_path / f"{version}-{environment}.json",
            release_verification_path=lambda version, environment: tmp_path / f"{version}-{environment}-verification.json",
            root=tmp_path,
            rel=lambda path: str(path),
            utc_now=lambda: "2026-04-03T00:00:00+00:00",
            write_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
            read_state=lambda slug: {},
            write_state=lambda slug, payload: None,
            replace_frontmatter_status=lambda path, status: None,
            json_dumps=lambda payload: json.dumps(payload),
        )
    except SystemExit as exc:
        assert "skip-verify" in str(exc)
    else:
        raise AssertionError("release promote deberia fallar si el provider exige verify.")
