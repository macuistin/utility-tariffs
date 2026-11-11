<!-- Title: Conventional Commits, type(scope): summary. For example: fix(sync): read the new workbook layout -->

## Summary

<!-- What does this change and why? Link the issue: Closes #n, or Part of #n. -->

## Changes

<!-- The notable changes, one bullet each. -->

-

## Testing

<!-- What you ran and on which Python, what the new tests cover, and what was not verified. -->

- [ ] `python3 -m scripts.build --check --base origin/main` passes
- [ ] `python3 -m unittest discover tests` passes on Python 3.14

## Impact

<!-- Effect on clients that read the store: paths, fields, checksums. Write "None" if there is none. -->

## Checklist

- [ ] The title follows Conventional Commits with a scope from `.claude/rules/docs-and-style.md`
- [ ] No published tariff revision is edited (a price change is a new numbered file)
- [ ] Indexes are rebuilt with `python3 -m scripts.build`, not edited by hand
- [ ] A bug fix has a test that fails without the fix
- [ ] Docs are updated (`docs/format.md`, `docs/design.md`, the source note)
