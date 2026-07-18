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


def pytest_col(cell):
    pt = cell.get('pytest', {})
    counts = pt.get('counts') or {}
    if not counts:
        return '—'
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
                        f'| {boot_col(cell)} | {pytest_col(cell)} |')
    header = ('| Target | NiceGUI | Install | Boot | Pytest (of collected) |\n'
              '|--------|---------|---------|------|-----------------------|')
    stamp = f'\n\n_Last run: {generated or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} · '
    stamp += 'Install = `uv sync` under PyPy · Boot = import + server + HTTP probe · '
    stamp += 'Pytest = upstream `uv run pytest` (browser tests included)._'
    return header + '\n' + '\n'.join(rows) + stamp


def make_badge(cells):
    booted = sum(1 for c in cells.values()
                 if c.get('install', {}).get('ok') and c.get('smoke', {}).get('ok'))
    total = len(PYPYS) * len(SOURCES)
    color = 'brightgreen' if booted == total else 'orange' if booted else 'red'
    return {'schemaVersion': 1, 'label': 'pypy compat',
            'message': f'{booted}/{total} boot', 'color': color}


def splice(readme_text, block):
    if START in readme_text and END in readme_text:
        head = readme_text.split(START)[0]
        tail = readme_text.split(END)[1]
        return f'{head}{START}\n{block}\n{END}{tail}'
    return readme_text.rstrip() + f'\n\n{START}\n{block}\n{END}\n'


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
