from __future__ import annotations

from pathlib import Path

from flowctl import release


def test_release_verify_runs_release_blocking_profiles(tmp_path: Path) -> None:
    payload = release._verify_release_from_manifest(
        version="v1.0.0",
        environment="staging",
        manifest={
            "repos": {},
            "features": [
                {
                    "slug": "demo-feature",
                    "verification_matrix": [
                        {
                            "name": "workspace-ok",
                            "level": "integration",
                            "command": "python3 -c \"print('ok')\"",
                            "blocking_on": ["release"],
                            "environments": ["staging"],
                        }
                    ],
                }
            ],
        },
        root=tmp_path,
        utc_now=lambda: "2026-04-03T00:00:00+00:00",
        require_pipelines=False,
    )

    assert payload["status"] == "passed"
    assert payload["features"][0]["verification_profiles"][0]["status"] == "passed"


def test_release_verify_fails_when_release_blocking_profile_fails(tmp_path: Path) -> None:
    payload = release._verify_release_from_manifest(
        version="v1.0.0",
        environment="production",
        manifest={
            "repos": {},
            "features": [
                {
                    "slug": "demo-feature",
                    "verification_matrix": [
                        {
                            "name": "workspace-fail",
                            "level": "e2e",
                            "command": "python3 -c \"import sys; sys.exit(3)\"",
                            "blocking_on": ["release"],
                            "environments": ["production"],
                        }
                    ],
                }
            ],
        },
        root=tmp_path,
        utc_now=lambda: "2026-04-03T00:00:00+00:00",
        require_pipelines=False,
    )

    assert payload["status"] == "failed"
    assert payload["features"][0]["verification_profiles"][0]["status"] == "failed"
    assert any("demo-feature" in item for item in payload["findings"])
