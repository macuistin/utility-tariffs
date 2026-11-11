---
description: "Writing, docs, commits, pull requests and branches"
---

# Docs, writing and workflow

## Writing

- UK English everywhere: code comments, docs, strings, commits (behaviour, colour, licence).
- Short sentences, action verbs, concrete names (files, fields, functions). A paragraph over
  three sentences is usually overwritten.
- No em dash to bolt on an afterthought. Use a comma or a full stop, or reword.
- A comment says why, never what the next line does. Delete commented-out code.

## Docs are generic

`README.md`, `docs/`, `sources/`, `skills/` and every issue and pull request are written for
anyone, in any country, with any supplier. They never mention the maintainer, one household's
bill, a personal name, an address, a serial number or a private link. Describe a setting by its
meaning and its unit, with a round-number example.

## Python

- Standard library only in `lib/tariffstore` and `scripts`. Type hints on every function.
- A function does one thing. Aim for 20 lines, never over 40.
- Raise an exception rather than return an error code. Catch specific exceptions.
- Money is `Decimal` or a decimal string, never a float.

## Naming commits, pull requests and issues

One form for all three, Conventional Commits: `type(scope): summary`.

- **Type:** `feat` (something new), `fix` (something wrong), `docs`, `test`, `refactor` (no
  change in behaviour), `ci`, `chore` (upkeep, and every scheduled sync).
- **Scope**, the part of the repo, one of: `tariffs` (the data), `schema` (the format and its
  validator), `build` (the indexes), `sync` (the sync path and sources), `client` (finding,
  fetching, caching, custom tariffs), `engine` (work needed in the bill engine), `prices`
  (dynamic prices), `sources` (source notes and research), `ci`, `repo` (settings, licences,
  these rules). Leave the scope out only when a change truly spans the repo.
- **Summary:** lower case, imperative, no full stop, under about 70 characters. Name the thing in
  plain words: `fix(sync): read the Ofgem workbook link from the new page layout`.
- A parent issue takes the same form and says the outcome: `feat(prices): publish dynamic
  half-hourly prices`. A decision to make is `docs(repo): decide ...` or the scope it settles.
- A pull request title is the commit message its merge deserves. It names the change, not the
  issue number. Link the issue in the body with `Closes #n` or `Part of #n`.
- A scheduled sync uses `chore(tariffs): sync <date>`.

## Commits and pull requests

- No `Co-Authored-By` line and no "Generated with" line in commits, pull requests, issues or
  comments. If a tool adds one, edit it out.
- Pull request body: `.github/PULL_REQUEST_TEMPLATE.md` (Summary, Changes, Testing, Impact,
  Checklist). List what was not verified under Testing.
- Related pull requests are stacked: each is based on the branch below it. Merge commits, not
  squash, so a stack stays mergeable.
- Never rebase, amend or force-push a branch that has an open pull request. Address review
  feedback with new commits on top.
- Nothing merges unless CI is green on the exact head commit. Check CI on `main` after a merge.

## Issues

- The plan lives in the issues: a parent issue for each area, child issues for each piece of
  work. Keep a child issue small enough for one pull request.
- Open one from a template in `.github/ISSUE_TEMPLATE/`. An issue says what is wrong or missing,
  what done looks like, and where the code is.
- A tariff that is wrong or missing names the country, the provider, the tariff and the link
  where the right figures are published.
