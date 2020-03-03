# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Miscellaneous utilities to assist with testing"""

import glob
import gzip
import inspect
import shutil
import stat
from json import dumps
import os
import re
import tempfile
import platform
import multiprocessing
import logging
import random
import socket
import textwrap
import warnings
from fnmatch import fnmatch
import time
from difflib import unified_diff
from contextlib import contextmanager
from unittest.mock import patch

from http.server import (
    HTTPServer,
    SimpleHTTPRequestHandler,
)

from functools import wraps
from os.path import (
    curdir,
    exists,
    join as opj,
    pardir,
    realpath,
    relpath,
    split as pathsplit,
)

from nose.plugins.attrib import attr
from nose.tools import (
    assert_equal,
    assert_false,
    assert_greater,
    assert_greater_equal,
    assert_in as in_,
    assert_in,
    assert_is,
    assert_is_none,
    assert_is_not,
    assert_is_not_none,
    assert_not_equal,
    assert_not_in,
    assert_not_is_instance,
    assert_raises,
    assert_true,
    eq_,
    make_decorator,
    ok_,
    raises,
)

from nose.tools import assert_set_equal
from nose.tools import assert_is_instance
from nose import SkipTest

import datalad.utils as ut
# TODO this must go
from ..utils import *
from datalad.utils import (
    Path,
    ensure_unicode,
)

from ..cmd import Runner
from .. import utils
from ..support.exceptions import CommandNotAvailableError
from ..support.vcr_ import *
from ..support.keyring_ import MemoryKeyring
from ..support.network import RI
from ..dochelpers import exc_str, borrowkwargs
from ..cmdline.helpers import get_repo_instance
from ..consts import (
    ARCHIVES_TEMP_DIR,
)

import pytest


# dj: if content is None, tmpdir.join("afile.txt") could be used (?)
@pytest.fixture(scope="function")
def with_tempfile_pyt(tmpdir):
    """Decorator function to provide a temporary file name and remove it at the end

    Parameters
    ----------

    To change the used directory without providing keyword argument 'dir' set
    DATALAD_TESTS_TEMP_DIR.

    Examples
    --------

    """
    path = tmpdir.join("afile.txt")
    def _create_file(content=None):
        if content:
            with open(path, 'w' + ('b' if isinstance(content, bytes) else '')) as f:
                f.write(content)
        return str(path)

    return _create_file