#!/usr/bin/env python3
"""Validate EN->ES documentation mirrors for SoftOS docs.

Rules:
- Canonical docs live at docs/*.md (excluding docs/es/*).
- Each canonical doc must have docs/es/<name>.es.md.
- Canonical doc should reference its Spanish mirror.
- Spanish mirror should reference its English source.

Supports changed-only mode for CI pull requests.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
DOCS_ES_DIR = DOCS_DIR / "es"

# Transitional exclusions for legacy docs not yet migrated to bilingual policy.
EXCLUDED_CANONICAL_DOCS = {
    "documentation-i18n-policy.md",
}


def run_git_diff_names(base: str, head: str) -> list[Path]:
    cmd = ["git", "diff", "--name-only", f"{base}..{head}"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"failed to list changed files for {base}..{head}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    if not out:
        return []
    return [REPO_ROOT / line.strip() for line in out.splitlines() if line.strip()]


def canonical_docs_all() -> list[Path]:
    docs: list[Path] = []
    if not DOCS_DIR.is_dir():
        return docs
    for path in sorted(DOCS_DIR.glob("*.md")):
        if path.name in EXCLUDED_CANONICAL_DOCS:
            continue
        docs.append(path)
    return docs


def canonical_docs_changed(base: str, head: str) -> list[Path]:
    changed = run_git_diff_names(base, head)
    canonical: set[Path] = set()
    for path in changed:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        parts = rel.parts
        if not parts:
            continue
        if parts[0] != "docs":
            continue
        if len(parts) == 2 and parts[1].endswith(".md"):
            if parts[1] not in EXCLUDED_CANONICAL_DOCS:
                canonical.add(REPO_ROOT / rel)
            continue
        if len(parts) == 3 and parts[1] == "es" and parts[2].endswith(".es.md"):
            en_name = parts[2].replace(".es.md", ".md")
            if en_name in EXCLUDED_CANONICAL_DOCS:
                continue
            canonical.add(DOCS_DIR / en_name)
    return sorted(canonical)


def expected_es_path(en_path: Path) -> Path:
    return DOCS_ES_DIR / f"{en_path.stem}.es.md"


def rel_link(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, start=from_path.parent).replace("\\", "/")


def validate_pair(en_path: Path) -> list[str]:
    errors: list[str] = []
    es_path = expected_es_path(en_path)
    if not en_path.is_file():
        errors.append(f"missing canonical English doc: {en_path.relative_to(REPO_ROOT)}")
        return errors
    if not es_path.is_file():
        errors.append(
            "missing Spanish mirror for "
            f"{en_path.relative_to(REPO_ROOT)}: expected {es_path.relative_to(REPO_ROOT)}"
        )
        return errors

    en_text = en_path.read_text(errors="replace")
    es_text = es_path.read_text(errors="replace")

    es_rel = rel_link(en_path, es_path)
    en_rel = rel_link(es_path, en_path)
    if es_rel not in en_text:
        errors.append(
            f"English doc {en_path.relative_to(REPO_ROOT)} must link Spanish mirror path {es_rel}"
        )
    if en_rel not in es_text:
        errors.append(
            f"Spanish doc {es_path.relative_to(REPO_ROOT)} must link English source path {en_rel}"
        )

    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Base commit for changed-only validation")
    parser.add_argument("--head", help="Head commit for changed-only validation")
    parser.add_argument("--changed", action="store_true", help="Validate only changed docs inferred from base/head")
    parser.add_argument(
        "--audit-all",
        action="store_true",
        help="Audit all canonical docs and print missing mirrors without failing",
    )
    args = parser.parse_args(argv)

    if args.changed and args.audit_all:
        raise SystemExit("--changed and --audit-all are mutually exclusive")
    if args.changed and (not args.base or not args.head):
        raise SystemExit("--changed requires --base and --head")

    docs = canonical_docs_changed(args.base, args.head) if args.changed else canonical_docs_all()

    if args.audit_all:
        missing: list[str] = []
        for doc in docs:
            es_path = expected_es_path(doc)
            if not es_path.is_file():
                missing.append(
                    f"{doc.relative_to(REPO_ROOT)} -> expected {es_path.relative_to(REPO_ROOT)}"
                )
        print("docs i18n legacy audit:")
        print(f"- canonical_docs: {len(docs)}")
        print(f"- missing_mirrors: {len(missing)}")
        for item in missing:
            print(f"- {item}")
        return 0

    errors: list[str] = []
    for doc in docs:
        errors.extend(validate_pair(doc))

    if errors:
        print("docs i18n validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    if args.changed:
        print(f"docs i18n validation passed for changed docs ({len(docs)} canonical docs)")
    else:
        print(f"docs i18n validation passed ({len(docs)} canonical docs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
