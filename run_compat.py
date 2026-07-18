#!/usr/bin/env python3
"""Probe NiceGUI compatibility under PyPy for ONE matrix cell.

Runs on the CI runner's own CPython and drives `uv` to build a PyPy environment,
then exercises NiceGUI in stages: resolve -> install -> smoke -> pytest.

It ALWAYS writes a structured JSON result and exits 0. A PyPy incompatibility is
recorded as *data* (which stage failed, which dependency, a log tail), never a
bare red X. The workflow only goes red on genuine infrastructure faults.

Stdlib only, so it runs regardless of what is installed.
"""
from __future__ import annotations

import argparse
import json
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

# Dependencies most likely to decide PyPy compat (Rust/pyo3/C-ext).
DEP_HINTS = ['pydantic-core', 'pydantic_core', 'watchfiles', 'orjson', 'lxml',
             'uvloop', 'httptools', 'greenlet', 'cffi', 'numpy', 'pillow',
             'aiohttp', 'selenium', 'maturin']


class _Abort(Exception):
    """Raised to short-circuit a failed stage; the result is still written."""


def run(cmd, cwd=None, timeout=None):
    """Run a command, capture combined stdout+stderr, never raise on non-zero."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout or ''
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.output or '') + f'\n[TIMEOUT after {timeout}s]'
    except FileNotFoundError as exc:
        return 127, f'[command not found: {exc}]'


def tail(text, n=4000):
    return (text or '')[-n:]


def latest_pypi_version():
    with urllib.request.urlopen(PYPI_JSON, timeout=30) as resp:
        return json.load(resp)['info']['version']


def guess_failed_dep(log):
    """Best-effort extraction of the dependency that failed to build/install."""
    low = (log or '').lower()
    hits = []
    for dep in DEP_HINTS:
        near = re.escape(dep) + r'.{0,80}(failed|error|no\s+wheel|not\s+supported|unsupported)'
        pre = r'(failed to build|building|error).{0,80}' + re.escape(dep)
        if re.search(near, low) or re.search(pre, low):
            hits.append(dep)
    for match in re.findall(r'failed to build[`\' ]+([a-z0-9_.\-]+)', low):
        hits.append(match)
    ordered = []
    for hit in hits:
        norm = hit.replace('_', '-')
        if norm not in ordered:
            ordered.append(norm)
    return ', '.join(ordered[:4]) or None


def parse_pytest(log):
    """Pull collected/passed/failed/skipped/error counts from pytest output."""
    counts = {}
    match = re.search(r'collected (\d+) item', log or '')
    if match:
        counts['collected'] = int(match.group(1))
    for kind in ['passed', 'failed', 'skipped', 'error', 'errors',
                 'xfailed', 'xpassed', 'deselected']:
        found = re.findall(r'(\d+)\s+' + kind + r'\b', log or '')
        if found:
            counts['error' if kind == 'errors' else kind] = int(found[-1])
    return counts


def do_smoke(ng: Path):
    """import nicegui, boot a real server, HTTP-probe the index page."""
    rc, log = run(['uv', 'run', 'python', '-c',
                   "import nicegui; print('NG', nicegui.__version__)"],
                  cwd=str(ng), timeout=300)
    if rc != 0:
        return False, 'import failed: ' + tail(log, 1200)

    app = ng / '_smoke_app.py'
    app.write_text(
        'from nicegui import ui\n'
        "@ui.page('/')\n"
        'def index():\n'
        "    ui.label('ngpypy-smoke-ok')\n"
        f'ui.run(port={SMOKE_PORT}, show=False, reload=False)\n')

    proc = subprocess.Popen(['uv', 'run', 'python', '_smoke_app.py'], cwd=str(ng),
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
    parser.add_argument('--source', required=True, choices=['pypi', 'main'])
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
        'pytest': {'ok': None, 'detail': None, 'counts': {}},
    }

    workdir = Path(tempfile.mkdtemp(prefix='ngpypy-'))
    ng = workdir / 'nicegui'
    try:
        # ---- resolve ref ----
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

        # ---- install PyPy + full dev env via uv ----
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
        rc, log = run(['uv', 'sync', '--python', args.pypy], cwd=str(ng), timeout=1800)
        if rc != 0:
            result['install'] = {'ok': False, 'failed_dep': guess_failed_dep(log),
                                 'detail': tail(log, 3000)}
            raise _Abort
        result['install'] = {'ok': True, 'failed_dep': None, 'detail': 'uv sync ok'}

        # ---- smoke ----
        ok, detail = do_smoke(ng)
        result['smoke'] = {'ok': ok, 'detail': detail}

        # ---- pytest (mirrors upstream `uv run pytest`; Chrome is on the runner) ----
        rc, log = run(['uv', 'run', 'pytest', '-q', '--color=no', '-p', 'no:cacheprovider'],
                      cwd=str(ng), timeout=2700)
        result['pytest'] = {'ok': rc == 0, 'returncode': rc,
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
        summary = {k: result[k] for k in ('pypy', 'source', 'resolve', 'install', 'smoke', 'pytest')}
        print(json.dumps(summary, indent=2, default=str)[:2500])
    sys.exit(0)


if __name__ == '__main__':
    main()
