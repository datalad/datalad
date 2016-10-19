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
from datalad.distribution.utils import _get_flexible_source_candidates_for_submodule

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
    eq_(f('../r', '.'), ['../r'])
    eq_(f('../r', 'ssh://host/path'), ['ssh://host/r'])
    eq_(f('sub', 'ssh://host/path'), ['ssh://host/path/sub'])
    eq_(f('../r', 'http://e.c/p'), ['http://e.c/r', 'http://e.c/r/.git'])
    eq_(f('sub', 'http://e.c/p'), ['http://e.c/p/sub', 'http://e.c/p/sub/.git'])

    # tricky ones
    eq_(f('sub', 'http://e.c/p/.git'), ['http://e.c/p/sub/.git'])
    eq_(f('../s1/s2', 'http://e.c/p/.git'), ['http://e.c/s1/s2/.git'])

    # incorrect ones will stay incorrect
    eq_(f('../s1/s2', 'http://e.c/.git'), ['http://e.c/../s1/s2/.git'])

    # when source is not relative, but base_url is specified as just the destination path,
    # not really a "base url" as name was suggesting, then it should be ignored
    eq_(f('http://e.c/p', '/path'), ['http://e.c/p', 'http://e.c/p/.git'])


@with_tempfile
@with_tempfile
def test_get_flexible_source_candidates_for_submodule(t, t2):
    f = _get_flexible_source_candidates_for_submodule
    # for now without mocking -- let's just really build a dataset
    from datalad.api import create
    from datalad.api import install
    ds = create(t)
    clone = install(t2, source=t)

    # first one could just know about itself or explicit url provided
    sshurl = 'ssh://e.c'
    httpurl = 'http://e.c'
    sm_httpurls = [httpurl, httpurl + '/.git']
    eq_(f(ds, 'sub'), [])
    eq_(f(ds, 'sub', sshurl), [sshurl])
    eq_(f(ds, 'sub', httpurl), sm_httpurls)
    eq_(f(ds, 'sub', None), [])  # otherwise really we have no clue were to get from

    # but if we work on dsclone then it should also add urls deduced from its
    # own location default remote for current branch
    eq_(f(clone, 'sub'), [t + '/sub'])
    eq_(f(clone, 'sub', sshurl), [t + '/sub', sshurl])
    eq_(f(clone, 'sub', httpurl), [t + '/sub'] + sm_httpurls)
    eq_(f(clone, 'sub'), [t + '/sub'])  # otherwise really we have no clue were to get from
    # TODO: check that http:// urls for the dataset itself get resolved

    # TODO: many more!!