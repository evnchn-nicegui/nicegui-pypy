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

PYPYS = ['pypy3.10', 'pypy3.11']
SOURCES = ['pypi', 'main']
START = '<!-- COMPAT:START -->'
END = '<!-- COMPAT:END -->'


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
    counts = (cell.get('pytest', {}) or {}).get('counts') or {}
    if not counts:
        return mark('na')
    collected = counts.get('collected')
    parts = []
    for key, glyph in (('passed', '✅'), ('failed', '❌'), ('error', '💥'), ('skipped', '⏭')):
        if counts.get(key):
            parts.append(f'{counts[key]}{glyph}')
    body = ' '.join(parts) if parts else '0'
    return f'{body} / {collected} collected' if collected is not None else body


def render_matrix(cells):
    generated = None
    rows = []
    for source in SOURCES:
        for pypy in PYPYS:
            cell = cells.get((pypy, source))
            if cell is None:
                rows.append(f'| `{pypy}` · {source} | — | — | — | — |')
                continue
            generated = generated or cell.get('generated_at')
            ref = cell.get('nicegui_ref') or '?'
            sha = cell.get('nicegui_sha')
            ref_txt = f'`{ref}`' + (f' (`{sha}`)' if source == 'main' and sha else '')
            if not cell.get('resolve', {}).get('ok', True):
                rows.append(f'| `{pypy}` · {source} | {ref_txt} | {mark("infra")} resolve | — | — |')
                continue
            ic, idetail = install_col(cell)
            rows.append(f'| `{pypy}` · {source} | {ref_txt} | {ic}{idetail} '
                        f'| {boot_col(cell)} | {tests_col(cell)} |')
    header = ('| Target | NiceGUI | Install | Boot | Pytest (of collected) |\n'
              '|--------|---------|---------|------|-----------------------|')
    stamp = f'\n\n_Last run: {generated or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} · '
    stamp += 'Install = NiceGUI runtime under PyPy · Boot = import + server + HTTP probe · '
    stamp += 'Pytest = NiceGUI suite via a minimal harness (heavy pandas/polars/matplotlib '
    stamp += 'integration deps omitted — no PyPy wheels)._'
    return header + '\n' + '\n'.join(rows) + stamp


def make_badge(cells):
    # Count only declared matrix cells, so a stray/foreign JSON can't push the
    # numerator past the fixed denominator (e.g. an impossible "5/4 boot").
    booted = 0
    for pypy in PYPYS:
        for source in SOURCES:
            c = cells.get((pypy, source)) or {}
            if c.get('install', {}).get('ok') and c.get('smoke', {}).get('ok'):
                booted += 1
    total = len(PYPYS) * len(SOURCES)
    color = 'brightgreen' if booted == total else 'orange' if booted else 'red'
    return {'schemaVersion': 1, 'label': 'pypy compat',
            'message': f'{booted}/{total} boot', 'color': color}


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
