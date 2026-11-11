# Contributing

The store is data anyone may correct. A change arrives as a pull request that passes CI.

## Fix or add a tariff

1. Read `docs/format.md`.
2. Never edit a published revision. Add the next numbered file beside it, with the date the new
   prices start. A new tariff starts at `1.json` in a new folder.
3. Run `python3 -m scripts.build`, then `python3 -m scripts.build --check --base origin/main`
   and `python3 -m unittest discover tests`.
4. Open a pull request that links where the figures are published.

If you would rather not write the file, open an issue from the "A tariff is wrong or missing"
template.

## Naming

Commits, pull request titles and issue titles use Conventional Commits: `type(scope): summary`.

| Type | For |
| --- | --- |
| `feat` | Something new: a tariff, a source, a field, a function |
| `fix` | Something wrong: a price, a parser, a bug |
| `docs`, `test`, `refactor`, `ci` | What they say |
| `chore` | Upkeep, and every scheduled sync |

Scopes: `tariffs`, `schema`, `build`, `sync`, `client`, `engine`, `prices`, `sources`, `ci`,
`repo`. For example `fix(tariffs): correct the night rate of an Irish tariff` or
`feat(sync): read the Ontario regulated rates`.

## Rules

`CLAUDE.md` and `.claude/rules/` hold the rules for the code, the data, the tests and the
workflows. They are written for AI assistants and apply to everyone.
