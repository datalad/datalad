# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test distribution utils

"""

import os
from os.path import join as opj

from datalad.distribution.utils import _get_flexible_source_candidates
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    assert_raises,
    eq_,
    known_failure_windows,
    with_tempfile,
)
from datalad.utils import (
    on_windows,
    unlink,
)


@known_failure_windows
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
