---
description: "CI and the scheduled sync workflow"
paths:
  - ".github/**"
---

# Workflows

- `ci.yml` runs on every pull request and on `main`: the build check against the base, then the
  tests with coverage. It needs no secret and has read-only permissions.
- `sync.yml` runs weekly and by hand. It reads every scheduled source, and when a price changed it
  opens one pull request. A new one closes the older one. A failed source opens or updates one
  `sync-failed` issue, titled `fix(sync): a source failed in the scheduled run`.
- A workflow never merges, never pushes to `main`, never approves a pull request and never
  creates a release.
- A pull request opened with the built-in token does not start workflows, so `sync.yml` starts
  CI on its branch itself. Keep that step unless a `SYNC_TOKEN` secret is set.
- Pass a workflow input or any text from an issue, a branch or a commit to a script through
  `env`, never inline in `run:`.
- Give each job the least permissions it needs, and a timeout.
- Pin an action to a major version from a publisher already used here. Do not add a third-party
  action for something a few lines of shell can do.
- Machine-written data that nobody can review, such as dynamic prices, goes to its own branch.
  It never reaches `main` without a pull request.
- Do not run the Sync workflow or change repository settings unless the maintainer asks.
