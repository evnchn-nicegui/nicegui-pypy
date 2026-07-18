#!/usr/bin/env python3
"""Aggregate per-cell result JSONs into the README matrix + a shields badge.

Reads every ``*.json`` under --in, rewrites the block between the
``<!-- COMPAT:START -->`` / ``<!-- COMPAT:END -->`` markers in the README, and
writes a shields.io endpoint badge.json ("N/4 boot", coloured by how many cells
install-and-boot). Stdlib only.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time

PYPY_TARGETS = ['pypy3.10', 'pypy3.11']
CONTROLS = ['3.11']  # CPython — comparison baseline; NOT counted in the badge
INTERPS = PYPY_TARGETS + CONTROLS
SOURCES = ['pypi', 'main']
START = '<!-- COMPAT:START -->'
END = '<!-- COMPAT:END -->'


def label(interp):
    return f'CPython {interp} *(control)*' if interp in CONTROLS else f'`{interp}`'


def load(indir):
    cells = {}
    for path in glob.glob(os.path.join(indir, '**', '*.json'), recursive=True):
        try:
            data = json.load(open(path))
            cells[(data['pypy'], data['source'])] = data
        except Exception:  # noqa: BLE001 - skip unreadable/foreign json
            continue
    return cells


def mark(state):
    return {'ok': '✅', 'fail': '❌', 'na': '—', 'infra': '🔧'}[state]


def install_col(cell):
    inst = cell.get('install', {})
    if inst.get('ok') is True:
        return mark('ok'), ''
    if inst.get('ok') is False:
        dep = inst.get('failed_dep')
        return mark('fail'), (f' ({dep})' if dep else '')
    return mark('na'), ''


def boot_col(cell):
    ok = cell.get('smoke', {}).get('ok')
    return mark('ok') if ok is True else mark('fail') if ok is False else mark('na')


def tests_col(cell):
    # Test-harness install must succeed before pytest can run.
    te = cell.get('test_env', {})
    if te.get('ok') is False:
        dep = te.get('failed_dep')
        return 'test-deps ' + mark('fail') + (f' ({dep})' if dep else '')
    counts = (cell.get('pytest', {}) or {}).get('counts')
    if not isinstance(counts, dict) or not counts:
        return mark('na')
    collected = counts.get('collected')
    parts = []
    for key, glyph in (('passed', '✅'), ('failed', '❌'), ('error', '💥'), ('skipped', '⏭')):
        if counts.get(key):
            parts.append(f'{counts[key]}{glyph}')
    body = ' '.join(parts) if parts else '0'
    return f'{body} / {collected} collected' if collected is not None else body


def _counts(cell):
    c = ((cell or {}).get('pytest', {}) or {}).get('counts')
    return c if isinstance(c, dict) else {}


def parity_suffix(cells, interp, source):
    """For a PyPy target, a one-glance 'matches CPython control?' verdict.

    Parity requires passed AND failed AND error counts to all be within noise of
    the control — not just the passed count (a close pass count with diverging
    failures would otherwise be mislabelled a match).
    """
    if interp not in PYPY_TARGETS:
        return ''
    mine, ctrl = _counts(cells.get((interp, source))), _counts(cells.get(('3.11', source)))
    if 'passed' not in mine or 'passed' not in ctrl:
        return ''

    def close(key):
        a, b = mine.get(key, 0), ctrl.get(key, 0)
        return abs(a - b) <= max(5, b // 100)

    if all(close(k) for k in ('passed', 'failed', 'error')):
        return ' · **≈ CPython ✓**'
    dp = mine.get('passed', 0) - ctrl.get('passed', 0)
    return (f' · vs CPython {ctrl.get("passed", 0)}✅/{ctrl.get("failed", 0)}❌ '
            f'(Δpass {dp:+d})')


def render_matrix(cells):
    generated = None
    rows = []
    for source in SOURCES:
        for interp in INTERPS:
            cell = cells.get((interp, source))
            row_label = f'{label(interp)} · {source}'
            if cell is None:
                rows.append(f'| {row_label} | — | — | — | — |')
                continue
            generated = generated or cell.get('generated_at')
            ref = cell.get('nicegui_ref') or '?'
            sha = cell.get('nicegui_sha')
            ref_txt = f'`{ref}`' + (f' (`{sha}`)' if source == 'main' and sha else '')
            if not cell.get('resolve', {}).get('ok', True):
                rows.append(f'| {row_label} | {ref_txt} | {mark("infra")} resolve | — | — |')
                continue
            ic, idetail = install_col(cell)
            tests = tests_col(cell) + parity_suffix(cells, interp, source)
            rows.append(f'| {row_label} | {ref_txt} | {ic}{idetail} '
                        f'| {boot_col(cell)} | {tests} |')
    header = ('| Target | NiceGUI | Install | Boot | Pytest (of collected) |\n'
              '|--------|---------|---------|------|-----------------------|')
    stamp = f'\n\n_Last run: {generated or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} · '
    stamp += 'Install = NiceGUI runtime · Boot = import + server + HTTP probe · '
    stamp += 'Pytest = NiceGUI suite via a minimal harness (heavy pandas/polars/matplotlib '
    stamp += 'integration deps omitted — no PyPy wheels). The **CPython 3.11 control** runs the '
    stamp += 'identical harness — compare its counts to isolate PyPy-specific failures from '
    stamp += 'harness/ordering artifacts._'
    return header + '\n' + '\n'.join(rows) + stamp


def make_badge(cells):
    # Target is PyPy 3.11+. Green only if the newest tracked PyPy installs + boots
    # on BOTH sources (release and main) — a partial (one source) pass is not green.
    ok = all((cells.get(('pypy3.11', s)) or {}).get('install', {}).get('ok')
             and (cells.get(('pypy3.11', s)) or {}).get('smoke', {}).get('ok')
             for s in SOURCES)
    return {'schemaVersion': 1, 'label': 'NiceGUI on PyPy 3.11',
            'message': 'installs + boots' if ok else 'not working',
            'color': 'brightgreen' if ok else 'red'}


def splice(readme_text, block):
    starts, ends = readme_text.count(START), readme_text.count(END)
    if starts == 0 and ends == 0:  # first run / markerless README: append a block
        return readme_text.rstrip() + f'\n\n{START}\n{block}\n{END}\n'
    # Refuse to edit a README whose markers are ambiguous — fail loud rather than
    # silently dropping content between the wrong pair.
    if starts != 1 or ends != 1 or readme_text.index(START) > readme_text.index(END):
        raise SystemExit(f'README compat markers malformed: {starts} START / {ends} END')
    head = readme_text.split(START, 1)[0]
    tail = readme_text.split(END, 1)[1]
    return f'{head}{START}\n{block}\n{END}{tail}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='indir', required=True)
    parser.add_argument('--readme', required=True)
    parser.add_argument('--badge', required=True)
    args = parser.parse_args()

    cells = load(args.indir)
    block = render_matrix(cells)

    readme = open(args.readme).read() if os.path.exists(args.readme) else '# nicegui-pypy\n'
    open(args.readme, 'w').write(splice(readme, block))
    open(args.badge, 'w').write(json.dumps(make_badge(cells)))
    print(f'rendered {len(cells)} cell(s); badge={make_badge(cells)["message"]}')


if __name__ == '__main__':
    main()
