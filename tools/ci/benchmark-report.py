#!/usr/bin/env python3
"""Summarize `asv compare --split` output as a Markdown report

The report lists benchmarks which got significantly slower or faster, or
which fail, and contains the full comparison in a collapsed section.  It is
meant for the GitHub job summary and a PR comment, e.g.::

    asv compare --split --factor 1.2 refs/bm/merge-target refs/bm/pr > compare.txt
    benchmark-report.py --factor 1.2 compare.txt > report.md

With --github-output, the number of benchmarks per category is also written
as `slower`, `faster`, `failing`, `failing_before` and `incomparable`, plus
`notable` (`true` if any benchmark is slower, faster or failing, or if there
are notes), in the format of $GITHUB_OUTPUT.
"""

import argparse
import math
import os
import re
import sys
from typing import NamedTuple

# Section titles printed by `asv compare`, with --split and without it
SECTIONS = {
    'Benchmarks that have improved:': 'improved',
    'Benchmarks that have stayed the same:': 'same',
    'Benchmarks that have got worse:': 'worse',
    'Benchmarks that are not comparable:': 'incomparable',
    'All benchmarks:': 'all',
}

# Meaning of the marks in the "Change" column of `asv compare`
MARKS = {
    '+': 'slower',
    '-': 'faster',
    '!': 'failing',
    '*': 'failing before',
    'x': 'not comparable',
}

# GitHub refuses comments longer than 65536 characters
MAX_LENGTH = 60000

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')


class Row(NamedTuple):
    section: str
    mark: str
    before: str
    after: str
    ratio: str
    name: str

    @property
    def ratio_value(self) -> float:
        try:
            return float(self.ratio.lstrip('~'))
        except ValueError:
            return math.nan

    @property
    def ratio_text(self) -> str:
        # tabulate drops trailing zeros if all ratios of a table are numbers
        value = self.ratio_value
        if math.isnan(value):
            return self.ratio
        return ('~' if self.ratio.startswith('~') else '') + f'{value:.2f}'

    @property
    def fails(self) -> bool:
        return self.mark == '!' or self.after == 'failed'

    @property
    def change(self) -> str:
        return 'failing' if self.fails else MARKS.get(self.mark, '')


def parse(text: str) -> tuple[list[str], list[Row]]:
    """Return the header and all rows of the tables in `asv compare` output

    Raises ValueError if the output does not look as expected, so that a
    change of its format cannot hide results.
    """
    header: list[str] = []
    rows: list[Row] = []
    section = ''
    sections_seen = []
    for line in text.splitlines():
        line = ANSI_ESCAPE.sub('', line).strip()
        if line in SECTIONS:
            section = SECTIONS[line]
            sections_seen.append(section)
            continue
        if not line.startswith('|'):
            continue
        cells = line[1:].removesuffix('|').split('|')
        if len(cells) < 5:
            continue
        # a "|" within a benchmark name (parameter) would split it
        cells = [c.strip() for c in cells[:4]] + ['|'.join(cells[4:]).strip()]
        if all(c and set(c) <= set('-:') for c in cells):
            # header separator
            continue
        if cells[0] == 'Change':
            header = cells
            continue
        rows.append(Row(section, *cells))

    # asv prints the title only of a non-empty section
    for section in sections_seen:
        if not any(r.section == section for r in rows):
            raise ValueError(f'Found no results in section {section!r}')
    for r in rows:
        if r.section == 'worse' and r.mark not in ('+', '!'):
            raise ValueError(f'Unexpected mark {r.mark!r} among benchmarks which got worse')
        if r.section not in ('worse', 'all', '') and r.mark in ('+', '!'):
            raise ValueError(f'Unexpected mark {r.mark!r} outside of benchmarks which got worse')
    return header, rows


def get_hash(header_cell: str) -> str:
    match = re.search(r'\[([0-9a-f]+)\]', header_cell)
    return match.group(1) if match else ''


def md_code(text: str) -> str:
    """Format as code for a table cell, where "|" must be escaped even then"""
    return '`' + text.replace('|', '\\|') + '`'


def md_table(rows: list[Row], before: str, after: str) -> list[str]:
    lines = [
        f'| Benchmark | {before} | {after} | Ratio |',
        '|---|--:|--:|--:|',
    ]
    lines.extend(
        f'| {md_code(r.name)} | {r.before} | {r.after} | {r.ratio_text} |'
        for r in rows
    )
    return lines


def md_full_table(rows: list[Row], before: str, after: str) -> list[str]:
    lines = [
        f'| Change | Benchmark | {before} | {after} | Ratio |',
        '|---|---|--:|--:|--:|',
    ]
    lines.extend(
        f'| {r.change} | {md_code(r.name)} '
        f'| {r.before} | {r.after} | {r.ratio_text} |'
        for r in rows
    )
    return lines


def ratio_key(r: Row, nan: float) -> float:
    value = r.ratio_value
    return nan if math.isnan(value) else value


def categorize(rows: list[Row]) -> dict[str, list[Row]]:
    # A ratio of "n/a" for a slower/faster benchmark means a time of 0 on one
    # side, sort those first
    return {
        'slower': sorted(
            (r for r in rows if r.mark == '+'),
            key=lambda r: ratio_key(r, math.inf), reverse=True),
        'faster': sorted(
            (r for r in rows if r.mark == '-'),
            key=lambda r: ratio_key(r, -math.inf)),
        # newly failing ("!") as well as failing on both sides
        'failing': [r for r in rows if r.fails],
        'failing_before': [r for r in rows if r.mark == '*'],
        'incomparable': [r for r in rows if r.mark == 'x'],
    }


def make_report(
        text: str,
        factor: str,
        before_label: str = 'the first revision',
        after_label: str = 'the second revision',
        notes: str = '',
) -> tuple[str, dict[str, list[Row]]]:
    header, rows = parse(text)
    if not rows:
        raise ValueError('No benchmark results found in the asv compare output')
    categories = categorize(rows)
    before_hash = get_hash(header[1]) if header else ''
    after_hash = get_hash(header[2]) if header else ''
    before = f'{before_label} `{before_hash}`' if before_hash else before_label
    after = f'{after_label} `{after_hash}`' if after_hash else after_label

    counts = []
    for category in ('slower', 'failing', 'faster'):
        if categories[category]:
            counts.append(f'{len(categories[category])} {category}')
    if categories['slower'] or categories['failing']:
        headline = '⚠️ Benchmarks: ' + ', '.join(counts)
    elif categories['faster']:
        headline = '🚀 Benchmarks: ' + ', '.join(counts)
    elif notes.strip():
        headline = '⚠️ Benchmarks: no significant changes among those compared'
    else:
        headline = '✅ Benchmarks: no significant changes'

    out = [f'## {headline}']
    for note in notes.strip().splitlines():
        out += ['', f'> ⚠️ {note}']

    sections = [
        ('slower', '🐢 Slower', None),
        ('faster', '🚀 Faster', None),
        ('failing', '❌ Failing',
         f'Those failing for {before_label} too are not caused by '
         f'{after_label}, but still fail the job.'),
        ('failing_before', 'Failing only before',
         f'Likely they use functionality new in {after_label}.'),
        ('incomparable', 'Not comparable',
         'Their code differs between both sides.'),
    ]
    for category, title, description in sections:
        selected = categories[category]
        if not selected:
            continue
        out += ['', f'### {title} ({len(selected)})', '']
        if description:
            out += [description, '']
        out += md_table(selected, before, after)

    full = [
        '',
        '<details>',
        f'<summary>All {len(rows)} benchmarks</summary>',
        '',
        *md_full_table(sorted(rows, key=lambda r: r.name), before, after),
        '',
        f'Slower/faster: changed by more than a factor of {factor}, '
        'significantly so according to asv; `~`: beyond the factor, but not '
        f'significant.  Ratio: {after_label} relative to {before_label}.  CI '
        'timings are noisy, check close calls locally with `asv continuous`.',
        '',
        '</details>',
    ]
    report = '\n'.join(out + full) + '\n'
    if len(report) > MAX_LENGTH:
        report = '\n'.join(
            out + ['', '_Full comparison omitted: too long for a comment._']
        ) + '\n'
    return report, categories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        'compare_output',
        help='file with the output of `asv compare --split`, "-" for stdin')
    parser.add_argument(
        '--factor', default='1.1',
        help='factor which was given to `asv compare` (default: %(default)s)')
    parser.add_argument(
        '--before-label', default='the first revision',
        help='name of the first revision given to `asv compare` (default: %(default)s)')
    parser.add_argument(
        '--after-label', default='the second revision',
        help='name of the second revision given to `asv compare` (default: %(default)s)')
    parser.add_argument(
        '--notes', metavar='PATH',
        help='file with notes to include, one per line, if it exists')
    parser.add_argument(
        '--github-output', metavar='PATH',
        help='append counts per category to this file, e.g. $GITHUB_OUTPUT')
    args = parser.parse_args(argv)

    if args.compare_output == '-':
        text = sys.stdin.read()
    else:
        with open(args.compare_output, encoding='utf-8') as f:
            text = f.read()
    notes = ''
    if args.notes and os.path.exists(args.notes):
        with open(args.notes, encoding='utf-8') as f:
            notes = f.read()

    try:
        report, categories = make_report(
            text, args.factor, args.before_label, args.after_label, notes)
    except ValueError as e:
        parser.exit(1, f'{parser.prog}: error: {e}\n')
    sys.stdout.write(report)

    if args.github_output:
        notable = bool(notes.strip()) or any(
            categories[c] for c in ('slower', 'faster', 'failing'))
        with open(args.github_output, 'a', encoding='utf-8') as f:
            for category, selected in categories.items():
                f.write(f'{category}={len(selected)}\n')
            f.write(f'notable={str(notable).lower()}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
