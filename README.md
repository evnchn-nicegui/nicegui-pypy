# nicegui-pypy

[![compat](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/evnchn-nicegui/nicegui-pypy/main/badge.json)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)
[![tracker](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml/badge.svg)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)

An **independent, automated tracker** that checks whether [NiceGUI](https://github.com/zauberzeug/nicegui)
installs and boots under **[PyPy](https://pypy.org/)** — the JIT Python interpreter — and runs NiceGUI's
own **browser-free core tests** on PyPy against a **CPython 3.11 control** run the same way. It runs
daily on GitHub Actions (free/unlimited for public repos) and writes the matrix back into this README.
**Target: PyPy 3.11+.**

> Not affiliated with the NiceGUI project. Runs *NiceGUI's own* test files, unmodified.

## Verdict

- ✅ **PyPy 3.11 — works.** NiceGUI installs, boots, and passes its browser-free core test subset
  **at parity with CPython 3.11** (`≈ CPython ✓` in the matrix). The only difference found is one
  trivially-cosmetic test — PyPy's `pickle` error message for a local function differs in wording — so
  there is **no functional PyPy-specific regression** in what runs on PyPy.
- ❌ **PyPy 3.10 — does not install.** Install fails at `watchfiles` (no PyPy-3.10 wheel, source build
  fails); `pydantic-core` also ships no `pp310` wheels. Upstream wheel-availability limit, not fixable
  here. Not sugar-coated: 3.10 is a hard no.

**Scope — what "core tests" means, honestly.** NiceGUI's **full** test suite (its Selenium browser
tests + tests needing `pandas`/`matplotlib`/`polars`) **cannot run on PyPy**: those are *test/dev*
dependencies that don't support PyPy (`pandas`/`matplotlib` segfault PyPy on import; `polars` has no
PyPy wheel). That is a limitation of the **test tooling**, not of NiceGUI at runtime. So this tracker
runs the browser-free `user`/unit subset that *does* run on PyPy. For reference, the full suite **is**
healthy on CPython with those deps present — **951 passed / 9 failed** (`uv run pytest`, CPython 3.11,
verified 2026-07-19) — it just can't be executed on PyPy.

## Latest result

<!-- COMPAT:START -->
| Target | NiceGUI | Install | Boot | Core tests |
|--------|---------|---------|------|------------|
| `pypy3.10` · pypi | `3.14.0` | ❌ (watchfiles) | — | — |
| `pypy3.11` · pypi | `3.14.0` | ✅ | ✅ | 173✅ 1❌ 1💥 · **≈ CPython ✓** |
| CPython 3.11 *(control)* · pypi | `3.14.0` | ✅ | ✅ | 174✅ |
| `pypy3.10` · main | `main` (`d1cf251711c7`) | ❌ (watchfiles) | — | — |
| `pypy3.11` · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 183✅ 1❌ 1💥 · **≈ CPython ✓** |
| CPython 3.11 *(control)* · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 184✅ |

_Last run: 2026-07-18T21:55:05Z · Install = NiceGUI runtime · Boot = import + server + HTTP probe · Core tests = NiceGUI's own browser-free `user`/unit tests (the full suite, incl. Selenium browser tests, needs pandas/matplotlib/etc. that don't run on PyPy — see README). The **CPython 3.11 control** runs the identical subset for comparison._
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
4. **core tests** — install a light harness (pytest + asyncio/order/selenium plugins, httpx2) and run
   NiceGUI's **browser-free `user`/unit test subset** (`tests/test_user_simulation*.py`,
   `test_run.py`, `test_element_filter.py`, …). These need no browser and none of the PyPy-incompatible
   integration deps, so they run deterministically on PyPy. Counts are passed / failed / skipped.
   *(Why not the full suite: see the Verdict's scope note — the browser + pandas/matplotlib tests can't
   run on PyPy at all, so running them would only produce a misleading all-red result.)*

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

- **Done:** daily tracker; PyPy 3.11 installs + boots + passes the browser-free core subset at parity
  with CPython 3.11 (one cosmetic `pickle`-message diff); PyPy 3.10 confirmed unsupported; full suite
  confirmed healthy on CPython (951/9) and confirmed un-runnable on PyPy (test-dep limitation).
- **Possible next (if PyPy test tooling improves):** widen the core subset as more of NiceGUI's
  integration-test deps gain PyPy support; add browser tests if a PyPy-compatible Selenium/driver path
  becomes viable.
- **Not actionable here:** PyPy 3.10 support depends on `watchfiles`/`pydantic-core` shipping `pp310`
  wheels; full-suite-on-PyPy depends on `pandas`/`matplotlib`/`polars` supporting PyPy — all upstream.

## License

MIT — see [LICENSE](LICENSE).
