# nicegui-pypy

[![compat](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/evnchn-nicegui/nicegui-pypy/main/badge.json)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)
[![tracker](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml/badge.svg)](https://github.com/evnchn-nicegui/nicegui-pypy/actions/workflows/compat.yml)

An **independent, automated tracker** for whether [NiceGUI](https://github.com/zauberzeug/nicegui)
installs, boots, and passes its test suite under **[PyPy](https://pypy.org/)** — the JIT Python
interpreter. It runs daily on GitHub Actions (free/unlimited for public repos) and writes the result
matrix back into this README.

> Not affiliated with the NiceGUI project. This repo runs *NiceGUI's own* test suite unmodified;
> it just points a different interpreter at it.

## Latest result

<!-- COMPAT:START -->
| Target | NiceGUI | Install | Boot | Pytest (of collected) |
|--------|---------|---------|------|-----------------------|
| `pypy3.10` · pypi | `3.14.0` | ❌ (lxml, httptools, aiohttp) | — | — |
| `pypy3.11` · pypi | `3.14.0` | — | — | — |
| `pypy3.10` · main | `main` (`d1cf251711c7`) | ❌ (lxml, httptools, aiohttp) | — | — |
| `pypy3.11` · main | `main` (`d1cf251711c7`) | — | — | — |

_Last run: 2026-07-18T06:51:03Z · Install = `uv sync` under PyPy · Boot = import + server + HTTP probe · Pytest = upstream `uv run pytest` (browser tests included)._
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

For every matrix cell — **{PyPy 3.10, PyPy 3.11} × {latest PyPI release, git `main`}** (4 cells):

1. **resolve** — pick the NiceGUI ref (release → matching `v*` tag; `main` → HEAD) and clone it.
2. **install** — `uv sync` the full dev environment against the chosen PyPy (`uv` respects the PyPy
   dependency markers automatically). Build failures capture the offending package.
3. **smoke** — `import nicegui`, start a real `ui.run()` server, and HTTP-probe the index page.
4. **pytest** — run NiceGUI's suite exactly as upstream does (`uv run pytest`, Chrome available on the
   runner), recording collected / passed / failed / skipped counts.

A PyPy incompatibility is recorded as **data** (which stage, which dependency, a log tail) — the
per-cell runner always succeeds, so the workflow's own green/red means "the tracker ran", while the
**compat** badge and the matrix above carry the actual verdict.

## Reproduce locally

```bash
uv python install pypy3.11
python3 run_compat.py --pypy pypy3.11 --source pypi --out results/pypy3.11-pypi.json
python3 render_report.py --in results --readme README.md --badge badge.json
```

## License

MIT — see [LICENSE](LICENSE).
