# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test get action

"""

from os import pardir
from os.path import join as opj

from datalad.api import create
from datalad.api import get
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import CommandError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import serve_path_via_http
from datalad.utils import chpwd

from ..dataset import Dataset


def test_get_invalid_call():
    # - InsufficientArgumentsError
    # - FileNotInAnnexError, ...
    # - unknown source
    # - dataset has no annex
    raise SkipTest("TODO")


def test_get_single_file():
    raise SkipTest("TODO")


def test_get_multiple_files():
    raise SkipTest("TODO")


def test_get_recurse_dirs():
    raise SkipTest("TODO")


def test_get_recurse_subdatasets():
    raise SkipTest("TODO")


def test_get_install_missing_subdataset():
    raise SkipTest("TODO")
