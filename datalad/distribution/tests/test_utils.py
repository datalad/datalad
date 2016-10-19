# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test distribution utils

"""

import logging
import os

from os.path import join as opj
from os.path import isdir
from os.path import exists
from os.path import realpath
from os.path import basename
from os.path import dirname

from mock import patch

from datalad.distribution.utils import _get_flexible_source_candidates

from datalad.tests.utils import create_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_in
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_false
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import use_cassette
from datalad.tests.utils import skip_if_no_network
from datalad.utils import _path_
from datalad.utils import rmtree


def test_get_flexible_source_candidates():
    f = _get_flexible_source_candidates
    # for http and https (dummy transport) we should get /.git source added
    eq_(f('http://e.c'), ['http://e.c', 'http://e.c/.git'])
    eq_(f('http://e.c/s/p'), ['http://e.c/s/p', 'http://e.c/s/p/.git'])
    # for those candidates should be just the original address, since git
    # understands those just fine
    for s in ('http://e.c/.git',
              '/',
              'relative/path',
              'smallrelative',
              './neighbor',
              '../../look/into/parent/bedroom',
              'p:somewhere',
              'user@host:/full/path',
              ):
        eq_(_get_flexible_source_candidates(s), [s])
    # Now a few relative ones
    eq_(f('../r', base_url='.'), ['../r'])
    eq_(f('../r', base_url='ssh://host/path'), ['ssh://host/r'])
    eq_(f('sub', base_url='ssh://host/path'), ['ssh://host/path/sub'])
    eq_(f('../r', base_url='http://e.c/p'), ['http://e.c/r', 'http://e.c/r/.git'])
    eq_(f('sub', base_url='http://e.c/p'), ['http://e.c/p/sub', 'http://e.c/p/sub/.git'])

    # tricky ones
    eq_(f('sub', base_url='http://e.c/p/.git'), ['http://e.c/p/sub/.git'])
    eq_(f('../s1/s2', base_url='http://e.c/p/.git'), ['http://e.c/s1/s2/.git'])

    # incorrect ones will stay incorrect
    eq_(f('../s1/s2', base_url='http://e.c/.git'), ['http://e.c/../s1/s2/.git'])
