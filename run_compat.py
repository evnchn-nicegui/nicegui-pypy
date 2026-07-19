#!/usr/bin/env python3
"""Probe NiceGUI compatibility under PyPy for ONE matrix cell.

Runs on the CI runner's own CPython and drives `uv` to build a PyPy environment,
then exercises NiceGUI in decoupled stages so a slow/failing test-env build never
hides the headline "does it install and boot" signal:

    resolve -> install (NiceGUI runtime) -> smoke -> test-env -> pytest

Each stage records structured results; the script ALWAYS writes JSON and exits 0.
A PyPy incompatibility is *data* (which stage, which dependency, a log tail), never
a bare red X. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

NICEGUI_REPO = 'https://github.com/zauberzeug/nicegui.git'
PYPI_JSON = 'https://pypi.org/pypi/nicegui/json'
SMOKE_PORT = 8099

# Deps that decide PyPy compat (Rust/pyo3/C-ext) — used to attribute build failures.
DEP_HINTS = ['pydantic-core', 'pydantic_core', 'watchfiles', 'orjson', 'lxml',
             'uvloop', 'httptools', 'greenlet', 'cffi', 'numpy', 'pillow',
             'aiohttp', 'rpds-py', 'rpds_py', 'selenium', 'maturin', 'pandas',
             'polars', 'matplotlib']

# Minimal test harness to run NiceGUI's pytest suite (its config uses
# --driver Chrome via pytest-selenium, asyncio_mode=auto, pytest.mark.order, and
# httpx2 for starlette's testclient). Heavy optional integration deps
# (pandas/polars/matplotlib/plotly/...) are intentionally omitted — they have no
# PyPy wheels; their test modules are collection-errored and skipped via
# --continue-on-collection-errors so the rest of the suite still runs.
# Deps for the browser-free core subset (pytest-selenium/selenium are needed only
# so the repo's `--driver Chrome` addopt parses — no browser is actually launched).
TEST_DEPS = ['pytest', 'pytest-asyncio', 'pytest-order', 'pytest-selenium',
             'selenium', 'webdriver-manager', 'requests', 'httpx', 'httpx2', 'numpy']

# Curated subset of NiceGUI's own tests that runs on PyPy: real Selenium/Chrome
# **browser** tests (the `screen` fixture — the whole point: the browser side is
# exercised so devs don't hand-test it) PLUS the browser-free `user`/unit tests.
# It deliberately excludes the handful of modules needing PyPy-incompatible deps
# (pandas/matplotlib/altair) and the few modules that destabilise NiceGUI's full
# in-one-batch run. The complete suite is only runnable on CPython (see README).
CORE_TESTS = [
    # browser (Selenium/Chrome, `screen` fixture) — core element rendering
    'tests/test_label.py', 'tests/test_link.py', 'tests/test_button.py',
    'tests/test_element.py', 'tests/test_html.py', 'tests/test_markdown.py',
    'tests/test_chip.py', 'tests/test_input.py', 'tests/test_number.py',
    'tests/test_select.py', 'tests/test_notification.py', 'tests/test_card.py',
    'tests/test_tooltip.py',
    # browser-free `user`/unit
    'tests/test_element_filter.py', 'tests/test_forwarded_prefix.py',
    'tests/test_markdown_response.py', 'tests/test_run.py',
    'tests/test_sub_pages_match_path.py', 'tests/test_user_simulation_context.py',
    'tests/test_user_simulation.py',
]


class _Abort(Exception):
    """Short-circuit a failed stage; the result is still written."""


def run(cmd, cwd=None, timeout=None, env=None):
    """Run a command, capture combined stdout+stderr, never raise on non-zero."""
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        proc = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True, env=full_env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout or ''
    except subprocess.TimeoutExpired as exc:
        out = exc.output or ''
        if isinstance(out, bytes):  # text=True still yields bytes on timeout kill
            out = out.decode('utf-8', 'replace')
        return 124, out + f'\n[TIMEOUT after {timeout}s]'
    except FileNotFoundError as exc:
        return 127, f'[command not found: {exc}]'


def tail(text, n=4000):
    return (text or '')[-n:]


def latest_pypi_version():
    with urllib.request.urlopen(PYPI_JSON, timeout=30) as resp:
        return json.load(resp)['info']['version']


def guess_failed_dep(log):
    """Best-effort: the dependency uv reported as failing to build."""
    low = (log or '').lower()
    hits = []
    # uv's own phrasing is the most reliable signal.
    for match in re.findall(r'failed to build[`\' ]+([a-z0-9_.\-]+)', low):
        hits.append(match)
    if not hits:
        for dep in DEP_HINTS:
            near = re.escape(dep) + r'.{0,80}(failed|error|no\s+wheel|not\s+supported)'
            if re.search(near, low):
                hits.append(dep)
    ordered = []
    for hit in hits:
        norm = hit.replace('_', '-').strip('-.')
        if len(norm) >= 3 and norm not in ordered:  # drop line-wrap artifacts ("a")
            ordered.append(norm)
    return ', '.join(ordered[:3]) or None


def parse_pytest(log):
    counts = {}
    match = re.search(r'collected (\d+) item', log or '')
    if match:
        counts['collected'] = int(match.group(1))
    for kind in ['passed', 'failed', 'skipped', 'error', 'errors', 'xfailed',
                 'xpassed', 'deselected']:
        found = re.findall(r'(\d+)\s+' + kind + r'\b', log or '')
        if found:
            counts['error' if kind == 'errors' else kind] = int(found[-1])
    return counts


def venv_python(ng: Path) -> str:
    return str(ng / '.venv' / 'bin' / 'python')


def do_smoke(ng: Path):
    """import nicegui, boot a real server, HTTP-probe the index page."""
    py = venv_python(ng)
    rc, log = run([py, '-c', "import nicegui; print('NG', nicegui.__version__)"],
                  cwd=str(ng), timeout=300)
    if rc != 0:
        return False, 'import failed: ' + tail(log, 1200)

    (ng / '_smoke_app.py').write_text(
        'from nicegui import ui\n'
        "@ui.page('/')\n"
        'def index():\n'
        "    ui.label('ngpypy-smoke-ok')\n"
        f'ui.run(port={SMOKE_PORT}, show=False, reload=False)\n')

    proc = subprocess.Popen([py, '_smoke_app.py'], cwd=str(ng),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        detail = 'no response within timeout'
        for _ in range(40):
            time.sleep(0.5)
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ''
                return False, 'server exited early: ' + tail(out, 1200)
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{SMOKE_PORT}/', timeout=3) as resp:
                    body = resp.read().decode('utf-8', 'replace')
                    marker = 'ngpypy-smoke-ok' in body
                    ok = resp.status == 200 and (marker or '<title' in body.lower())
                    return ok, f'HTTP {resp.status}, {"marker found" if marker else "no marker"}'
            except Exception as exc:  # noqa: BLE001 - probe, keep polling
                detail = f'probe: {exc}'
        return False, detail
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pypy', required=True, help='e.g. pypy3.10 / pypy3.11')
    parser.add_argument('--source', required=True)  # validated inside try (choices would exit pre-JSON)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    result = {
        'pypy': args.pypy,
        'source': args.source,
        'nicegui_ref': None,
        'nicegui_sha': None,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'resolve': {'ok': None, 'detail': None},
        'install': {'ok': None, 'detail': None, 'failed_dep': None},
        'smoke': {'ok': None, 'detail': None},
        'test_env': {'ok': None, 'detail': None, 'failed_dep': None},
        'pytest': {'ok': None, 'detail': None, 'counts': {}},
    }

    workdir = Path(tempfile.mkdtemp(prefix='ngpypy-'))
    ng = workdir / 'nicegui'
    py = venv_python(ng)
    try:
        if args.source not in ('pypi', 'main'):
            result['resolve'] = {'ok': False, 'detail': f'invalid --source {args.source!r}'}
            raise _Abort
        # ---- resolve ref + clone (tests + main source come from git) ----
        if args.source == 'pypi':
            version = latest_pypi_version()
            ref = f'v{version}'
            result['nicegui_ref'] = version
        else:
            ref = 'main'
            result['nicegui_ref'] = 'main'
        rc, log = run(['git', 'clone', '--depth', '1', '--branch', ref,
                       NICEGUI_REPO, str(ng)], timeout=300)
        if rc != 0:
            result['resolve'] = {'ok': False, 'detail': f'clone {ref} failed: ' + tail(log, 800)}
            raise _Abort
        _, sha = run(['git', '-C', str(ng), 'rev-parse', 'HEAD'])
        result['nicegui_sha'] = sha.strip()[:12]
        result['resolve'] = {'ok': True, 'detail': ref}

        # ---- provision PyPy + venv ----
        rc, log = run(['uv', 'python', 'install', args.pypy], timeout=600)
        if rc != 0:
            result['install'] = {'ok': False, 'failed_dep': None,
                                 'detail': f'uv python install {args.pypy} failed: ' + tail(log, 1500)}
            raise _Abort
        rc, log = run(['uv', 'venv', '--python', args.pypy, '.venv'], cwd=str(ng), timeout=300)
        if rc != 0:
            result['install'] = {'ok': False, 'failed_dep': None,
                                 'detail': 'uv venv failed: ' + tail(log, 1500)}
            raise _Abort

        # ---- install NiceGUI runtime (the "does it install?" signal) ----
        if args.source == 'pypi':
            spec = [f'nicegui=={result["nicegui_ref"]}']
            env = None
        else:
            spec = ['.']  # build main from the clone
            env = {'POETRY_DYNAMIC_VERSIONING_BYPASS': '0.0.0'}  # shallow clone has no tags
        rc, log = run(['uv', 'pip', 'install', '--python', py] + spec,
                      cwd=str(ng), timeout=2400, env=env)
        if rc != 0:
            result['install'] = {'ok': False, 'failed_dep': guess_failed_dep(log),
                                 'detail': tail(log, 3000)}
            raise _Abort
        result['install'] = {'ok': True, 'failed_dep': None, 'detail': 'runtime installed'}

        # ---- smoke ----
        ok, detail = do_smoke(ng)
        result['smoke'] = {'ok': ok, 'detail': detail}

        # ---- test-env install (light; enough to run the browser-free core subset) ----
        rc, log = run(['uv', 'pip', 'install', '--python', py] + TEST_DEPS,
                      cwd=str(ng), timeout=1200)
        if rc != 0:
            result['test_env'] = {'ok': False, 'failed_dep': guess_failed_dep(log),
                                  'detail': tail(log, 2500)}
            raise _Abort
        result['test_env'] = {'ok': True, 'failed_dep': None, 'detail': 'test harness installed'}

        # ---- pytest: NiceGUI's own browser-free core subset ----
        # (The full suite needs pandas/matplotlib/etc. that can't run on PyPy; run
        # what genuinely runs, deterministically, rather than a broken partial run.)
        tests = [t for t in CORE_TESTS if (ng / t).is_file()]
        rc, log = run([py, '-m', 'pytest', '-q', '--color=no', '-p', 'no:cacheprovider']
                      + tests, cwd=str(ng), timeout=900)
        result['pytest'] = {'ok': rc == 0, 'returncode': rc, 'suite': 'browser-free core subset',
                            'counts': parse_pytest(log), 'detail': tail(log, 4000)}
    except _Abort:
        pass
    except Exception as exc:  # noqa: BLE001 - record anything unexpected
        result['error'] = repr(exc)
    finally:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))
        shutil.rmtree(workdir, ignore_errors=True)
        keys = ('pypy', 'source', 'resolve', 'install', 'smoke', 'test_env', 'pytest')
        print(json.dumps({k: result[k] for k in keys}, indent=2, default=str)[:2500])
    sys.exit(0)


if __name__ == '__main__':
    main()
