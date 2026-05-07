# Evidence Registry

Every workflow should keep an evidence registry that names the current artifact
for each gate and whether it is still valid for the current revision.

## Minimum registry

```md
| Evidence | Status | Revision | Path/Link | Owner | Notes |
| --- | --- | --- | --- | --- | --- |
| Spec | | | | | |
| Plan | | | | | |
| R1 | | | | | |
| R2 | | | | | |
| R3 | | | | | |
| R4 | | | | | |
| R5 | | | | | |
| E2E | | | | | |
| PR | | | | | |
| Deploy | | | | | |
| Communication | | | | | |
```

## Stale evidence rule

Any change to the reviewed diff or deployed revision can invalidate downstream
evidence. Profiles define which events invalidate which evidence, but by
default:

- spec change invalidates R1 and R2
- plan change invalidates R2
- code diff change invalidates R3 and R4
- deployed revision change invalidates E2E and R4
- PR head change invalidates exact-revision validation evidence
