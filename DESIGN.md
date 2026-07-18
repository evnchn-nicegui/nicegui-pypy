# nicegui-pypy — design

**What:** A public GitHub repo (`evnchn-nicegui/nicegui-pypy`) that continuously tracks whether
[NiceGUI](https://github.com/zauberzeug/nicegui) installs, boots, and passes its test suite under
**PyPy** (the JIT Python interpreter). Runs on GitHub Actions (free/unlimited for public repos) and
auto-writes a pass/fail matrix back into the README.

**Why it's non-trivial:** NiceGUI's transitive deps include Rust/pyo3-backed packages —
`pydantic-core` (via FastAPI), plus `watchfiles`, `orjson`, `uvloop`, `httptools` — whose PyPy wheel
availability is the crux. "Does NiceGUI even install and boot on PyPy" is a real, moving question.

## Decisions (operator-approved)

| Axis | Choice |
|------|--------|
| Test depth | **Full pytest suite**, as much as public CI + PyPy allow. Not all tests are expected to run under PyPy — showing *which* run is the point. Try to run more than the prior attempt did. |
| Matrix | **PyPy 3.10 + 3.11** × **{latest PyPI release, git main}** = 4 cells. |
| Cadence | **Daily cron** (06:00 UTC) + `workflow_dispatch` + push to `main`. |
| Output | **README status badge + auto-updated compat matrix**, incl. failing dep + traceback tail. |

## Architecture

Two-phase GitHub Actions workflow (`.github/workflows/compat.yml`):

### Phase 1 — `test` (matrix, 4 cells, `continue-on-error` so every cell always reports)
`{ pypy: [pypy3.10, pypy3.11] } × { source: [pypi, main] }`

Per cell, a runner (`run_compat.py`) executes staged and **always emits a structured JSON result**
(`results/<pypy>-<source>.json`), even on failure, so the tracker records *data* rather than just a
red X:

1. **resolve** — determine the NiceGUI ref: `pypi` → latest version from PyPI JSON API + matching
   git tag `v<ver>` for the test files; `main` → HEAD of `zauberzeug/nicegui@main`.
   (Tests live only in the git repo, not the wheel — so we always check out the repo for tests, and
   for the `pypi` cell install the *released* distribution, not source-at-tag.)
2. **install** — create the env; install NiceGUI (+ `[testing]` extras). Capture the exact failing
   package + error phrase if it can't build (the pydantic-core/pyo3 case).
3. **smoke** — `import nicegui`; start `ui.run()` in a subprocess; HTTP-probe `/` for 200 + `<title>`.
4. **pytest** — run the suite in **two buckets to maximise what runs** (the "break new ground" lever):
   - **browser-free** (NiceGUI's `user`-fixture / pure-Python tests) — highest chance on PyPy.
   - **browser** (`screen`-fixture, needs Playwright/Selenium + Chrome) — likely blocked; recorded
     separately so a browser-stack failure doesn't mask browser-free passes.
   Record `collected / passed / failed / skipped / errors` + a log tail per bucket.

Result JSON schema (per cell):
```json
{"pypy":"pypy3.11","source":"main","nicegui_ref":"vX.Y.Z / <sha>",
 "install":{"ok":false,"detail":"pydantic-core: no PyPy wheel, maturin build failed"},
 "smoke":{"ok":null},
 "pytest":{"browser_free":{"collected":0,"passed":0,"failed":0,"skipped":0,"errors":0,"tail":"..."},
           "browser":{...}}}
```

### Phase 2 — `report` (`needs: test`, runs even if cells failed)
- Download all cell artifacts.
- Render the matrix into `README.md` between `<!-- COMPAT:START -->` / `<!-- COMPAT:END -->`.
- Write `badge.json` (shields.io endpoint schema: e.g. `{"label":"pypy compat","message":"2/4 boot","color":"orange"}`).
- Commit README + badge.json back to `main` (`contents: write`, bot commit, `[skip ci]`).

### Badges (README, no external hosting)
1. Workflow-ran badge: `…/actions/workflows/compat.yml/badge.svg` — "did the tracker run today".
2. Compat badge: `shields.io/endpoint?url=<raw badge.json>` — "N/4 install+boot" (green/orange/red).

## Failure philosophy
A PyPy compat failure is **expected data, not a CI error**. Cells use `continue-on-error`; the runner
always exits 0 and records the failure. The workflow only goes red on an *infrastructure* fault
(runner crash, report step broken) — so the green/red of the workflow badge means "tracker healthy",
and the compat badge + matrix carry the actual compat verdict.

## Non-goals (YAGNI)
- No CPython control column for now (operator chose the 4-cell matrix). Easy to add later.
- No GitHub Pages dashboard (README matrix is the surface).
- No historical time-series (each run overwrites; git history is the record).

## Empirical-verification plan
Per house doctrine: don't claim "ready" until CI is actually green and the matrix is populated. After
push, trigger a run, watch it, iterate on the runner against real PyPy behaviour, and only then report.
The prior-attempt findings (mined from session `a1d0737a`) feed the install/pytest-bucket logic before
the first run.
