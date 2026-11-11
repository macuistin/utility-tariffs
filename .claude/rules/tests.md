---
description: "What each test file proves, rules for new tests, and the coverage floor"
paths:
  - "tests/**"
---

# Tests

`tests/README.md` lists what each file proves. Run `python3 -m unittest discover tests` from the
repository root.

- Python 3.14 runs everything. An older Python skips the tests that need the bill engine. Run
  3.14 before you say the suite passes, or say which Python you used.
- CI holds branch coverage of `lib/tariffstore` and `scripts` at 98% (`.coveragerc`). New code
  arrives with its tests. Do not add a `pragma: no cover` to reach the floor.
- No test fetches from the network. A source is tested on saved or synthetic responses through
  the replay fetcher.
- Test behaviour: call the function and assert on the result. Do not read a source file and
  assert a string is in it.
- Control time. Pass the date in. A test never depends on the day it runs.
- Use `tests/fixtures.py` for made-up tariffs and a store on disk. Paths come from
  `scripts/paths.py`, never the working directory.
- A bug fix has a test that fails without the fix. Name it in the pull request.
- Never weaken a test to get green: no deleted test, loosened assertion, `skip` or wider
  tolerance for a failure you caused. A test that is wrong is fixed in its own commit with the
  reason in the message.
- An expected figure says where it came from. `test_tariffs_through_lib.py` labels each one PAGE
  (from the source) or ASSUMPTION (chosen by the test). Work a hand calculation out in a comment.
- `test_stored_tariffs.py` and `test_tariffs_through_lib.py` run over every file in `tariffs/`.
  Compute counts from the files. Do not pin the number of tariffs, because a sync changes it.
- A new validator rule has a test for the refusal and one for the accepted form.
