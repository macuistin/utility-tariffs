# skills/

Steps for an AI assistant. None of them is in the update path: the scheduled sync is plain Python.

| Skill | Job |
| --- | --- |
| `find-sources/` | Look for new tariff and dynamic price sources and record them under `sources/`. Meant to run on a schedule. Research only |
| `sync-tariff/` | Add or correct one tariff by hand |

A skill opens a pull request. It never merges.
