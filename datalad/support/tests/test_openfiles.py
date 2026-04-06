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
from pathlib import Path
from unittest.mock import (
    MagicMock,
    patch,
)

import pytest

from datalad.tests.utils_pytest import (
    skip_if_no_psutil,
    with_tree,
)

from ..openfiles import (
    _is_write_mode,
    _lsof_get_write_files,
    get_files_open_for_writing,
)


def _hold_open(path, mode, seconds=30):
    """Spawn a subprocess that holds *path* open in *mode*."""
    proc = subprocess.Popen(
        [sys.executable, '-c',
         f'fh = open({str(path)!r}, {mode!r}); '
         f'import time; time.sleep({seconds})'])
    time.sleep(0.5)  # let the child actually open the file
    return proc


@skip_if_no_psutil
@pytest.mark.ai_generated
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

    # -- our own process IS detected (no self-exclusion) --
    fh = open(testfile, 'w')
    try:
        result = get_files_open_for_writing([str(testfile)])
        assert str(testfile) in result, \
            "Our own process should be detected"
    finally:
        fh.close()

    # -- read-only open should NOT be detected --
    proc_r = _hold_open(testfile, 'r')
    try:
        assert get_files_open_for_writing(
            [str(testfile)]) == {}, \
            "Read-only open must not be detected"
    finally:
        proc_r.terminate()
        proc_r.wait()

    # -- write open IS detected --
    proc_w = _hold_open(testfile, 'w')
    try:
        result = get_files_open_for_writing(
            [str(testfile)])
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
            [str(testfile)])
        assert str(testfile) in result, \
            f"Append-open file not detected: {result}"
    finally:
        proc_a.terminate()
        proc_a.wait()

    # -- r+ (read-write) IS detected --
    proc_rw = _hold_open(testfile, 'r+')
    try:
        result = get_files_open_for_writing(
            [str(testfile)])
        assert str(testfile) in result, \
            f"r+ open file not detected: {result}"
    finally:
        proc_rw.terminate()
        proc_rw.wait()

    # -- symlink resolved: querying via symlink still detects --
    link = tmp_path / "link.txt"
    link.symlink_to(testfile)
    proc_sym = _hold_open(testfile, 'w')
    try:
        result = get_files_open_for_writing(
            [str(link)])
        assert str(link) in result, \
            f"Symlink query should detect open file: {result}"
    finally:
        proc_sym.terminate()
        proc_sym.wait()


# -- Unit tests for helpers --------------------------------------------------


@pytest.mark.ai_generated
def test_is_write_mode():
    """Test _is_write_mode with various mode/flags combinations."""
    # mode string present
    f = MagicMock(mode='r', flags=None)
    assert _is_write_mode(f) is False
    f.mode = 'w'
    assert _is_write_mode(f) is True
    f.mode = 'a'
    assert _is_write_mode(f) is True
    f.mode = 'r+'
    assert _is_write_mode(f) is True
    f.mode = 'rb'
    assert _is_write_mode(f) is False

    # mode empty, flags present
    f = MagicMock(mode='', flags=os.O_RDONLY)
    assert _is_write_mode(f) is False
    f.flags = os.O_WRONLY
    assert _is_write_mode(f) is True
    f.flags = os.O_RDWR
    assert _is_write_mode(f) is True

    # neither mode nor flags
    f = MagicMock(spec=[])  # no attributes at all
    assert _is_write_mode(f) is None


@pytest.mark.ai_generated
def test_lsof_get_write_files():
    """Test lsof output parsing."""
    lsof_output = (
        "p1234\n"
        "fcwd\n"
        "ar\n"
        "n/some/read/file\n"
        "f3\n"
        "aw\n"
        "n/some/write/file\n"
        "f4\n"
        "au\n"
        "n/some/readwrite/file\n"
        "f5\n"
        "ar\n"
        "n/some/other/read\n"
    )
    with patch('subprocess.check_output', return_value=lsof_output):
        result = _lsof_get_write_files(1234)
    assert result == {'/some/write/file', '/some/readwrite/file'}


@pytest.mark.ai_generated
def test_lsof_get_write_files_unavailable():
    """Test lsof fallback when lsof is not installed."""
    with patch('subprocess.check_output', side_effect=FileNotFoundError):
        result = _lsof_get_write_files(1234)
    assert result is None


@pytest.mark.ai_generated
def test_lsof_get_write_files_timeout():
    """Test lsof fallback on timeout."""
    with patch('subprocess.check_output',
               side_effect=subprocess.TimeoutExpired('lsof', 10)):
        result = _lsof_get_write_files(1234)
    assert result is None


@skip_if_no_psutil
@pytest.mark.ai_generated
@with_tree({'testfile.txt': 'hello'})
def test_lsof_fallback_triggered(path=None):
    """When _is_write_mode returns None, lsof fallback should be used."""
    testfile = Path(path) / "testfile.txt"

    proc_w = _hold_open(testfile, 'w')
    try:
        resolved = str(testfile.resolve())
        lsof_output = f"p{proc_w.pid}\nf3\naw\nn{resolved}\n"
        with patch(
            'datalad.support.openfiles._is_write_mode', return_value=None
        ), patch(
            'subprocess.check_output', return_value=lsof_output
        ):
            result = get_files_open_for_writing(
                [str(testfile)])
        assert str(testfile) in result, \
            f"lsof fallback should detect write-open file: {result}"
    finally:
        proc_w.terminate()
        proc_w.wait()


# -- CLI tests ---------------------------------------------------------------


@skip_if_no_psutil
@pytest.mark.ai_generated
@with_tree({'quiet.txt': 'hello'})
def test_cli_no_open_files(path=None):
    """CLI reports no open files for a quiet directory."""
    testfile = Path(path) / 'quiet.txt'
    result = subprocess.run(
        [sys.executable, '-m', 'datalad.support.openfiles', str(testfile)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert 'No files open for writing' in result.stdout


@skip_if_no_psutil
@pytest.mark.ai_generated
@with_tree({'a.txt': 'a', 'b.txt': 'b'})
def test_cli_with_directory(path=None):
    """CLI expands directories to files."""
    result = subprocess.run(
        [sys.executable, '-m', 'datalad.support.openfiles', path],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert 'No files open for writing' in result.stdout


@skip_if_no_psutil
@pytest.mark.ai_generated
@with_tree({'busy.txt': 'hello'})
def test_cli_detects_open_file(path=None):
    """CLI exits with 1 and reports files open for writing."""
    testfile = Path(path) / 'busy.txt'
    proc = _hold_open(testfile, 'w')
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'datalad.support.openfiles',
             str(testfile)],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 1
        assert 'PIDs:' in result.stdout
    finally:
        proc.terminate()
        proc.wait()
