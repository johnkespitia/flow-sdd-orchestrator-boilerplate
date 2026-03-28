# Contributing

Thanks for contributing to this project.

## Development Setup

1. Fork the repository and create a feature branch from `main`.
2. Install dependencies and verify local tooling.
3. Run the quality gates before opening a PR.

Recommended checks:

```bash
python3 ./flow doctor
python3 ./flow ci spec --all --json
python3 ./flow ci repo --all --json
python3 ./flow ci integration --profile smoke:ci-clean --auto-up --json
python3 -m pytest gateway/tests -q
```

## Pull Requests

- Keep PRs focused and scoped.
- Add/update tests for behavior changes.
- Update docs/specs when contracts or workflows change.
- Use clear commit messages.

## Style and Scope

- Prefer spec-driven changes (`specs/**`) for new features.
- Avoid unrelated refactors in the same PR.
- Do not commit secrets, credentials, or generated local state.

## Questions

For design or implementation questions, open a GitHub issue with context and expected outcome.
