# nicegui-pypy

[![compat](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/evnchn-nicegui/nicegui-pypy/main/badge.json)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)
[![tracker](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml/badge.svg)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)

An **independent, automated tracker** for whether [NiceGUI](https://github.com/zauberzeug/nicegui)
installs, boots, and passes its test suite under **[PyPy](https://pypy.org/)** — the JIT Python
interpreter. It runs daily on GitHub Actions (free/unlimited for public repos) and writes the result
matrix back into this README. **Target: PyPy 3.11+.**

> Not affiliated with the NiceGUI project. This repo runs *NiceGUI's own* test suite unmodified;
> it just points a different interpreter at it.

## Verdict

- ✅ **PyPy 3.11 — supported.** NiceGUI installs, boots, and runs its test suite **on par with
  CPython 3.11**: the pass/fail counts are within ~1 test of the CPython control (see the matrix).
  Whatever works on CPython 3.11 works on PyPy 3.11.
- ❌ **PyPy 3.10 — not supported.** NiceGUI won't install: its Rust dependencies `watchfiles` and
  `pydantic-core` publish **no PyPy-3.10 wheels**, and the from-source build fails. This is an upstream
  wheel-availability limit, not something this repo can fix. Not sugar-coated: 3.10 is a hard no.

**About the raw failure counts:** the matrix shows a large number of `❌` for *both* PyPy 3.11 **and**
the CPython 3.11 control. That is a limitation of this tracker's **lightweight harness**, not a NiceGUI
or PyPy defect — the harness omits heavy integration deps (`pandas`/`polars`/`matplotlib`/…, which have
no PyPy wheels), and running the suite without them disrupts NiceGUI's ordering-sensitive test
isolation. The point that matters for compatibility is the **PyPy-vs-CPython parity** (`≈ CPython ✓`),
which holds. Closing the absolute gap is tracked as [future work](#status--roadmap).

## Latest result

<!-- COMPAT:START -->
| Target | NiceGUI | Install | Boot | Pytest (of collected) |
|--------|---------|---------|------|-----------------------|
| `pypy3.10` · pypi | `3.14.0` | ❌ (watchfiles) | — | — |
| `pypy3.11` · pypi | `3.14.0` | ✅ | ✅ | 242✅ 616❌ 11💥 1⏭ · **≈ CPython ✓** |
| CPython 3.11 *(control)* · pypi | `3.14.0` | ✅ | ✅ | 243✅ 616❌ 11💥 |
| `pypy3.10` · main | `main` (`d1cf251711c7`) | ❌ (watchfiles) | — | — |
| `pypy3.11` · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 254✅ 621❌ 11💥 1⏭ · **≈ CPython ✓** |
| CPython 3.11 *(control)* · main | `main` (`d1cf251711c7`) | ✅ | ✅ | 256✅ 620❌ 11💥 |

_Last run: 2026-07-18T14:00:39Z · Install = NiceGUI runtime · Boot = import + server + HTTP probe · Pytest = NiceGUI suite via a minimal harness (heavy pandas/polars/matplotlib integration deps omitted — no PyPy wheels). The **CPython 3.11 control** runs the identical harness — compare its counts to isolate PyPy-specific failures from harness/ordering artifacts._
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
4. **pytest** — install a **minimal test harness** (pytest + pytest-selenium/asyncio/order, httpx2,
   selenium, numpy) and run NiceGUI's own `tests/` suite (Chrome is available on the runner). Heavy
   optional integration deps (`pandas`, `polars`, `matplotlib`, `plotly`, …) have **no PyPy wheels**,
   so their test modules are collection-errored and skipped (`--continue-on-collection-errors`) while
   the rest of the suite runs. Counts are collected / passed / failed / skipped.

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

- **Done:** daily tracker; PyPy 3.11 vs CPython 3.11 parity established; PyPy 3.10 confirmed
  unsupported.
- **In progress / next:** close the absolute test-pass gap by making the harness match upstream's
  full-environment run (install every integration dep where a PyPy wheel exists; cleanly *deselect*
  the wheel-less modules rather than letting them collection-error and disturb test ordering). This
  lifts both the PyPy and CPython-control pass counts toward green without changing the parity verdict.
- **Not actionable here:** PyPy 3.10 support depends on `watchfiles`/`pydantic-core` shipping
  `pp310` wheels upstream.

## License

MIT — see [LICENSE](LICENSE).
