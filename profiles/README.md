# SoftOS Harness Profiles

Profiles bind the generic Harness Core to a specific organization, repository
set, delivery workflow, and toolchain.

A profile owns:

- ticket systems and work item key patterns
- repository mirror format
- labels and PR conventions
- staging/deploy/E2E strategy
- communication surfaces
- expected CI/check names
- reviewer/owner discovery rules
- redaction and privacy rules

Core policies must remain project-neutral. Profiles may include project-specific
conventions, but should avoid secrets and private links unless the profile is
kept private/local.
