# PR / Commit Readiness

The PR/commit readiness gate prevents avoidable review and CI churn.

## Required checks

- branch is scoped to the work item and is not the base branch
- commit list is reviewable and intentional
- PR title follows the profile's title lint convention
- PR body is complete without chat history
- linked ticket/spec/evidence are present
- labels are discovered from the target repository/profile, not guessed
- reviewers/owners are identified or explicitly deferred
- expected checks are known
- PR stays draft until required gates pass

## Readiness pack

```md
## Branch / Commit
- Target repo:
- Base branch:
- Feature branch:
- Commit message:
- Commit SHA(s):

## PR Metadata
- Title:
- Draft or ready:
- Labels discovered:
- Labels to apply:
- Reviewers/owners:
- Linked work item:
- Spec/evidence links:

## Expected Checks
- Title lint:
- Unit/lint/coverage:
- Docs/contract:
- Profile-specific checks:

## Verdict
- APPROVE_PR_CREATE / REQUEST_PR_CHANGES / BLOCK_PR_PUBLISHING
```
