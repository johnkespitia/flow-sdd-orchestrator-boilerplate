# Documentation i18n Policy (EN default + ES mirror)

Language pair policy for SoftOS workspace documentation.

## Scope

This policy applies to normative and operational documentation under `docs/**`,
policy packs under `policies/**`, and shared adoption docs under `profiles/**`.

## Default language

English is the canonical source for new and updated documentation.

- Canonical file: `docs/<topic>.md`
- Spanish mirror: `docs/es/<topic>.es.md`

For policy packs and profile docs, keep English in-place and add Spanish mirror
under a sibling `es/` folder when needed.

## Required behavior

1. Update English first for any feature, behavior, contract, or workflow change.
2. Update Spanish mirror in the same PR for user-facing or operational docs.
3. Add cross-links at the top of each pair:
   - English file links to Spanish mirror.
   - Spanish file links to English source.
4. Keep section order aligned between EN and ES to reduce drift.

## Recommended metadata

At the top of both EN and ES files, include:

- `Source`: path of canonical EN file.
- `Last updated`: UTC date.
- `Version`: optional release/spec marker.

## PR readiness

Documentation changes are considered complete only when:

- English canonical doc is updated.
- Spanish mirror exists and reflects the same operational meaning.
- Links between EN/ES versions are present.

## Notes

- This policy does not force translation of historical docs immediately.
- New docs and materially changed docs must follow this standard.
