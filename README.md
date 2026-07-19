# nicegui-pypy

[![compat](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/evnchn-nicegui/nicegui-pypy/main/badge.json)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)
[![tracker](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml/badge.svg)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)

An **independent, automated tracker** that checks whether [NiceGUI](https://github.com/zauberzeug/nicegui)
installs and boots under **[PyPy](https://pypy.org/)** — the JIT Python interpreter — and runs a subset
of NiceGUI's own tests, **including real Selenium/Chrome browser tests**, on PyPy against a **CPython
3.11 control** run the same way. It runs daily on GitHub Actions (free/unlimited for public repos) and
writes the matrix back into this README. **Target: PyPy 3.11+.**

> Not affiliated with the NiceGUI project. Runs *NiceGUI's own* test files, unmodified.

## Verdict

- ✅ **PyPy 3.11 — works, browser included.** NiceGUI installs, boots, and passes its core test subset
  — **real Selenium/Chrome browser tests** (the whole point: the rendered Vue/socket.io side is
  exercised, not just Python-simulated) plus `user`/unit tests — **at parity with CPython 3.11**
  (`≈ CPython ✓`). The only differences are a **handful of genuine PyPy semantics**: PyPy has no
  refcounting, so a couple of "object is collected immediately after delete" tests don't hold, and a
  `pickle` error message is worded differently. No functional rendering regression.
- ❌ **PyPy 3.10 — does not install.** Install fails at `watchfiles` (no PyPy-3.10 wheel, source build
  fails); `pydantic-core` also ships no `pp310` wheels. Upstream wheel-availability limit, not fixable
  here. Not sugar-coated: 3.10 is a hard no.

**Scope — honestly, what is and isn't covered.** The subset covers NiceGUI's core browser element
rendering + Python API. It does **not** cover the whole suite: a few test modules need
`pandas`/`matplotlib`/`altair` (which `segfault`/don't install on PyPy), and NiceGUI's full
all-in-one-batch run destabilises once any module is absent — so running *everything* on PyPy yields a
misleading all-red rather than signal. For reference, the **full** suite is healthy on CPython with all
deps present — **951 passed / 9 failed** (`uv run pytest`, CPython 3.11, verified 2026-07-19).

## Latest result

<!-- COMPAT:START -->
_⏳ Refreshing — the core subset now includes real Selenium/Chrome browser tests; the next run will
populate this matrix (expected: PyPy 3.11 ≈ CPython 3.11, minus a few genuine-PyPy diffs; PyPy 3.10
install ❌)._
<!-- COMPAT:END -->

## Why this is not trivial

NiceGUI is pure-Python, but its dependency tree includes packages backed by **Rust (pyo3/maturin)** and
**C**, whose PyPy wheel availability is the real question:

| Dependency | Kind | PyPy note |
|------------|------|-----------|
| `pydantic-core` | Rust / pyo3 | Direct NiceGUI dep **and** pulled via FastAPI. The make-or-break — does a PyPy wheel exist, or must it build from source? |
| `watchfiles` | Rust / pyo3 | Reload watcher; another maturin build under PyPy. |
| `lxml` | C (libxml2) | Usually ships PyPy wheels. |
| `orjson` | Rust | **Already excluded on PyPy** by NiceGUI's own marker (`platform_python_implementation != 'PyPy'`, [dependabot/83](https://github.com/zauberzeug/nicegui)) — NiceGUI falls back to stdlib JSON. |
| `uvloop` (via `uvicorn[standard]`) | Cython | Excluded on PyPy by uvicorn's own marker. |

Upstream NiceGUI has **no PyPy CI** — only the two exclusion markers above. So this tracker genuinely
breaks new ground rather than mirroring an existing pipeline.

## What each run does

For every matrix cell — **{PyPy 3.10, PyPy 3.11, CPython 3.11 *(control)*} × {latest PyPI release,
git `main`}** (6 cells). The **CPython 3.11 control** runs the *identical* harness, so comparing its
counts against PyPy's separates genuine PyPy-specific failures from harness/ordering artifacts (it is
**not** counted in the compat badge):

1. **resolve** — pick the NiceGUI ref (release → matching `v*` tag; `main` → HEAD) and clone it.
2. **install** — install the **NiceGUI runtime** into a PyPy venv (`uv pip install`). This is the
   headline "does it install?" signal; build failures capture the offending package. (Kept separate
   from the test-env build below so a slow/failing dev-dep build can't hide it.)
3. **smoke** — `import nicegui`, start a real `ui.run()` server, and HTTP-probe the index page.
4. **core tests** — install a light harness (pytest + asyncio/order/selenium plugins, httpx2,
   webdriver-manager) and run a curated subset of NiceGUI's own tests: **real Selenium/Chrome browser
   tests** for core elements (`test_label`, `test_button`, `test_input`, `test_element`, …) **plus**
   `user`/unit tests. Chrome is available on the runner. The subset excludes the few modules needing
   PyPy-incompatible deps and those that destabilise NiceGUI's full one-batch run. Counts are
   passed / failed / skipped. *(Why not the whole suite: see the Verdict's scope note.)*

A PyPy incompatibility is recorded as **data** (which stage, which dependency, a log tail) — the
per-cell runner always succeeds, so the workflow's own green/red means "the tracker ran", while the
**compat** badge and the matrix above carry the actual verdict.

## Reproduce locally

```bash
uv python install pypy3.11
python3 run_compat.py --pypy pypy3.11 --source pypi --out results/pypy3.11-pypi.json
python3 render_report.py --in results --readme README.md --badge badge.json
```

## Status & roadmap

- **Done:** daily tracker; PyPy 3.11 installs + boots + passes a browser-inclusive core subset (real
  Selenium/Chrome) at parity with CPython 3.11 (only genuine-PyPy diffs: GC/refcount, `pickle` message);
  PyPy 3.10 confirmed unsupported; full suite confirmed healthy on CPython (951/9).
- **Possible next:** widen the browser subset toward the full element set as it proves stable on PyPy;
  pull in more modules if their deps (`pandas`/`matplotlib`/`polars`) ever gain PyPy support.
- **Not actionable here:** PyPy 3.10 support depends on `watchfiles`/`pydantic-core` shipping `pp310`
  wheels; the pandas/matplotlib-class test modules depend on those libs supporting PyPy — all upstream.

## License

MIT — see [LICENSE](LICENSE).
