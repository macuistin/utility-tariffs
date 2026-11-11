---
description: "CI and the scheduled sync workflow"
paths:
  - ".github/**"
---

# Workflows

- `ci.yml` runs on every pull request and on `main`: the build check against the base, then the
  tests with coverage. It needs no secret and has read-only permissions.
- `sync.yml` runs weekly and by hand. Each source runs in its own job, so one that fails or
  hangs does not stop the others. The last job gathers what the successful ones wrote, builds
  the indexes once and opens one pull request when a price changed. A new one closes the older
  one.
- A source that failed gets its own `sync-failed` issue, titled `fix(sync): <source> failed in
  the scheduled run`. A later failure of the same source is a comment on the open issue. A
  failure is a thing to check, not a verdict on the source: read the run before changing code.
- Only the last job of `sync.yml` can write. The source jobs read the repository and nothing
  else.
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
