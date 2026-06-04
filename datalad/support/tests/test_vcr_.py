# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for vcr adapter"""

from pathlib import Path

from ...tests.utils_pytest import (
    SkipTest,
    eq_,
)
from ..vcr_ import (
    _get_cassette_path,
    use_cassette,
)


def test_get_cassette_path_absolute(tmp_path):
    # Absolute paths are returned unchanged
    abs_path = str(tmp_path / "foo.yaml")
    eq_(_get_cassette_path(abs_path), abs_path)


def test_get_cassette_path_caller_relative(tmp_path, monkeypatch):
    # When a versioned cassette exists next to the calling module under
    # `vcr_cassettes/<name>.yaml`, that path is returned.
    cassette_dir = Path(__file__).parent / "vcr_cassettes"
    cassette_dir.mkdir(exist_ok=True)
    cassette = cassette_dir / "test_get_cassette_path_caller_relative.yaml"
    cassette.write_text("interactions: []\nversion: 1\n")
    try:
        eq_(_get_cassette_path("test_get_cassette_path_caller_relative"),
            str(cassette))
    finally:
        cassette.unlink()
        # only remove the dir if we created it for this test
        try:
            cassette_dir.rmdir()
        except OSError:
            pass


def test_get_cassette_path_fallback(tmp_path, monkeypatch):
    # No caller-relative cassette -> legacy CWD-relative scratch path.
    # Use a unique-enough name so that no test shipping a cassette by
    # that name would shadow this assertion.
    name = "datalad_vcr_test_definitely_no_such_cassette_xyz"
    eq_(_get_cassette_path(name),
        "fixtures/vcr_cassettes/%s.yaml" % name)


def test_use_cassette_if_no_vcr():
    # just test that our do nothing decorator does the right thing if vcr is not present
    skip = False
    try:
        import vcr
        skip = True
    except ImportError:
        pass
    except:
        # if anything else goes wrong with importing vcr, we still should be able to
        # run use_cassette
        pass
    if skip:
        raise SkipTest("vcr is present, can't test behavior with vcr presence ATM")

    @use_cassette("some_path")
    def checker(x):
        return x + 1

    eq_(checker(1), 2)
