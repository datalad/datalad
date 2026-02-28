# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Detect files open for writing by other processes.

Provides :func:`get_files_open_for_writing` which checks whether any of the
given paths are held open for writing by another process.  Uses *psutil*.

Can also be invoked as ``python -m datalad.support.openfiles``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

lgr = logging.getLogger('datalad.support.openfiles')

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_files_open_for_writing(
    paths: list[str | Path],
    exclude_pids: set[int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return a mapping of *paths* that are open for writing.

    Parameters
    ----------
    paths
        File paths to check (absolute or relative – they will be resolved).
    exclude_pids
        PIDs to ignore.  If *None* the current process tree is excluded
        automatically to avoid false positives from our own open fds.

    Returns
    -------
    dict
        ``{original_path: [{'pid': int, 'fd': int}, ...]}`` for every path
        from *paths* that is currently open for writing by at least one
        process not in *exclude_pids*.

    Raises
    ------
    ImportError
        If *psutil* is not installed.
    """
    if psutil is None:
        raise ImportError(
            "psutil is required for open-file detection; "
            "install it with: pip install datalad[misc]")

    if not paths:
        return {}

    if exclude_pids is None:
        exclude_pids = _get_own_process_tree()

    # Build a lookup: resolved_path -> original_path
    resolved_to_orig: dict[str, str] = {}
    for p in paths:
        try:
            resolved = str(Path(p).resolve())
        except OSError:
            lgr.log(5, "Cannot resolve %r, skipping", p)
            continue
        resolved_to_orig[resolved] = str(p)

    if not resolved_to_orig:
        return {}

    lgr.log(5, "Checking %d path(s) for open-for-writing fds", len(resolved_to_orig))

    target_paths = set(resolved_to_orig)
    result: dict[str, list[dict[str, Any]]] = {}

    # Only inspect processes owned by the current user — other users'
    # processes would raise AccessDenied anyway and cannot conflict
    # with our git operations.
    my_uid = os.getuid()
    n_procs = 0
    n_skipped_uid = 0

    for proc in psutil.process_iter(['pid', 'uids']):
        try:
            pid = proc.info['pid']
            proc_uids = proc.info['uids']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if pid in exclude_pids:
            continue
        # Skip processes owned by other users
        if proc_uids is not None and proc_uids.real != my_uid:
            n_skipped_uid += 1
            continue
        n_procs += 1
        try:
            open_files = proc.open_files()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            if lgr.isEnabledFor(logging.DEBUG):
                _proc_info = _describe_process(proc)
                lgr.debug("Cannot read open files of %s: %s", _proc_info, exc)
            continue
        for f in open_files:
            if f.path not in target_paths:
                continue
            mode = getattr(f, 'mode', '')
            if lgr.isEnabledFor(logging.DEBUG):
                _proc_info = _describe_process(proc)
                lgr.debug("Target file %s open by %s mode=%r fd=%s",
                          f.path, _proc_info, mode, getattr(f, 'fd', '?'))
            if mode and any(c in mode for c in ('w', 'a', '+')):
                orig = resolved_to_orig.get(f.path, f.path)
                result.setdefault(orig, []).append(
                    {'pid': pid,
                     'fd': getattr(f, 'fd', -1)})

    lgr.log(5, "Scanned %d procs (skipped %d other-user), "
               "found %d path(s) open for writing",
            n_procs, n_skipped_uid, len(result))

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _describe_process(proc: psutil.Process) -> str:
    """Return a short description of *proc* for log messages."""
    try:
        cmdline = proc.cmdline()
        cmd = ' '.join(cmdline) if cmdline else '?'
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        cmd = '?'
    try:
        username = proc.username()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        username = '?'
    return f"pid {proc.pid} ({cmd!r}, user={username})"


def _get_own_process_tree() -> set[int]:
    """Return PIDs of the current process and all its children."""
    me = psutil.Process()
    pids = {me.pid}
    try:
        for child in me.children(recursive=True):
            pids.add(child.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    lgr.log(5, "Own process tree: %s", pids)
    return pids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description='Show files open for writing under given paths.')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='Files or directories to check.  Directories '
                             'are automatically expanded to all files '
                             'underneath.')
    args = parser.parse_args()

    paths: list[str] = []
    for p in args.paths:
        if os.path.isdir(p):
            # TODO: consider skipping .git/ and other VCS dirs, or
            # limiting to files that would be subject to commit
            for root, _dirs, files in os.walk(p):
                paths.extend(os.path.join(root, f) for f in files)
        else:
            paths.append(p)

    result = get_files_open_for_writing(paths)
    if result:
        for path, openers in sorted(result.items()):
            pids = ', '.join(str(o['pid']) for o in openers)
            print(f'{path}  (PIDs: {pids})')
        sys.exit(1)
    else:
        print('No files open for writing.')


if __name__ == '__main__':
    _cli_main()
