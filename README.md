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
  (`≈ CPython ✓`). No functional rendering regression.
- ❌ **PyPy 3.10 — does not install.** Install fails at `watchfiles` (no PyPy-3.10 wheel, source build
  fails); `pydantic-core` also ships no `pp310` wheels. Upstream wheel-availability limit, not fixable
  here. Not sugar-coated: 3.10 is a hard no.

**Three tests are excluded on both interpreters** because they assert **CPython-only semantics** and
cannot pass on PyPy *by design* — the two `test_no_cyclic_references_*` tests rely on CPython
refcounting to free acyclic garbage synchronously (PyPy has no refcounting), and one test asserts
CPython's exact `pickle`-error wording. A fix is proposed upstream in
[**evnchn/nicegui#210**](https://github.com/evnchn/nicegui/pull/210) (`skipif`-PyPy + a wider regex);
once it lands, the tracker runs them again automatically. Excluding them keeps the PyPy-vs-CPython
comparison to *portable* behaviour.

**Scope.** The subset covers NiceGUI's core browser-element rendering + Python API — not the whole
suite: a few modules need `pandas`/`polars`, which **can't run on PyPy** (see the test-dependency table
below), and NiceGUI's full all-in-one-batch run destabilises once any module is absent. For reference,
the **full** suite is healthy on CPython with all deps present — **951 passed / 9 failed** (`uv run
pytest`, CPython 3.11, verified 2026-07-19).

## Latest result

<!-- COMPAT:START -->
| Target | NiceGUI | Install | Boot | Core tests |
|--------|---------|---------|------|------------|
| `pypy3.10` · pypi | `3.14.0` | ❌ (watchfiles) | — | — |
| `pypy3.11` · pypi | `3.14.0` | ✅ | ✅ | 314✅ 1❌ · **≈ CPython ✓** |
| CPython 3.11 *(control)* · pypi | `3.14.0` | ✅ | ✅ | 315✅ |
| `pypy3.10` · main | `main` (`d1cf251711c7`) | ❌ (watchfiles) | — | — |
| `pypy3.11` · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 325✅ · **≈ CPython ✓** |
| CPython 3.11 *(control)* · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 325✅ |

_Last run: 2026-07-20T08:32:26Z · Install = NiceGUI runtime · Boot = import + server + HTTP probe · Core tests = NiceGUI's own suite subset — real **Selenium/Chrome browser** element tests + `user`/unit tests (the full suite also needs pandas/matplotlib-class deps that don't run on PyPy — see README). The **CPython 3.11 control** runs the identical subset._
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

## Test-dependency PyPy support (what gates the *test* coverage)

NiceGUI's runtime installs on PyPy 3.11; what limits how much of the **test suite** can run is whether
its optional integration deps work on PyPy (all verified on PyPy 3.11, 2026-07-19):

| Dep | On PyPy 3.11 | Effect on the tracker |
|-----|--------------|-----------------------|
| `numpy` | ✅ works (2.4.x wheel) | in the harness; numpy-using tests run |
| `matplotlib` | ✅ works (3.11.x, imports clean) | no PyPy blocker (the one `ui.pyplot` test is excluded for an unrelated refcounting reason, see #210) |
| `pandas` | ❌ **`import pandas` → SIGSEGV** (exit 139) | blocks `test_table`/`test_aggrid`/`test_altair`; **upstream *pandas* bug**, not NiceGUI's |
| `polars` | ❌ no PyPy wheel | blocks polars-path tests; upstream *polars* |

So "getting the rest working" is mostly done — numpy and matplotlib already run; only `pandas`- and
`polars`-dependent tests are out, and both are upstream-library limits (a pandas SIGSEGV on PyPy, and a
missing polars wheel) that neither this repo nor NiceGUI can fix.

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
   PyPy-incompatible deps, and **deselects 3 CPython-only-semantics tests** (see the Verdict — fix in
   [#210](https://github.com/evnchn/nicegui/pull/210)). Counts are passed / failed / skipped.
   *(Why not the whole suite: see the Verdict's scope note.)*

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
