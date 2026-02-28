# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for openfiles detection."""

import os
import subprocess
import sys
import time

import pytest

from ..openfiles import get_files_open_for_writing


def _hold_open(path, mode, seconds=30):
    """Spawn a subprocess that holds *path* open in *mode*."""
    proc = subprocess.Popen(
        [sys.executable, '-c',
         f'fh = open({str(path)!r}, {mode!r}); '
         f'import time; time.sleep({seconds})'])
    time.sleep(0.5)  # let the child actually open the file
    return proc


def test_get_files_open_for_writing(tmp_path):
    """Check various scenarios in a single tmp_path to avoid per-test overhead."""
    testfile = tmp_path / "testfile.txt"
    testfile.write_text("hello")

    # -- empty input --
    assert get_files_open_for_writing([]) == {}

    # -- nonexistent path --
    assert get_files_open_for_writing(['/no/such/file/anywhere']) == {}

    # -- file exists but not open --
    assert get_files_open_for_writing([str(testfile)]) == {}

    # -- our own process is excluded by default --
    fh = open(testfile, 'w')
    try:
        assert get_files_open_for_writing([str(testfile)]) == {}, \
            "Our own process tree should be excluded"
    finally:
        fh.close()

    # In the remaining checks we pass exclude_pids={os.getpid()} so that
    # child-spawned helpers are *not* silently excluded (the default
    # _get_own_process_tree() would hide them since they are our children).
    only_self = {os.getpid()}

    # -- read-only open should NOT be detected --
    proc_r = _hold_open(testfile, 'r')
    try:
        assert get_files_open_for_writing(
            [str(testfile)], exclude_pids=only_self) == {}, \
            "Read-only open must not be detected"
    finally:
        proc_r.terminate()
        proc_r.wait()

    # -- write open IS detected --
    proc_w = _hold_open(testfile, 'w')
    try:
        result = get_files_open_for_writing(
            [str(testfile)], exclude_pids=only_self)
        assert str(testfile) in result, \
            f"Write-open file not detected: {result}"
        assert any(o['pid'] == proc_w.pid for o in result[str(testfile)])
    finally:
        proc_w.terminate()
        proc_w.wait()

    # -- append open IS detected --
    proc_a = _hold_open(testfile, 'a')
    try:
        result = get_files_open_for_writing(
            [str(testfile)], exclude_pids=only_self)
        assert str(testfile) in result, \
            f"Append-open file not detected: {result}"
    finally:
        proc_a.terminate()
        proc_a.wait()

    # -- r+ (read-write) IS detected --
    proc_rw = _hold_open(testfile, 'r+')
    try:
        result = get_files_open_for_writing(
            [str(testfile)], exclude_pids=only_self)
        assert str(testfile) in result, \
            f"r+ open file not detected: {result}"
    finally:
        proc_rw.terminate()
        proc_rw.wait()

    # -- explicit exclude_pids hides the opener --
    proc_ex = _hold_open(testfile, 'w')
    try:
        result = get_files_open_for_writing(
            [str(testfile)], exclude_pids={proc_ex.pid, os.getpid()})
        assert result == {}, \
            f"Excluded PID should not appear: {result}"
    finally:
        proc_ex.terminate()
        proc_ex.wait()

    # -- symlink resolved: querying via symlink still detects --
    link = tmp_path / "link.txt"
    link.symlink_to(testfile)
    proc_sym = _hold_open(testfile, 'w')
    try:
        result = get_files_open_for_writing(
            [str(link)], exclude_pids=only_self)
        assert str(link) in result, \
            f"Symlink query should detect open file: {result}"
    finally:
        proc_sym.terminate()
        proc_sym.wait()
