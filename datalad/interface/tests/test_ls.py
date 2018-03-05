# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Primarily a smoke test for ls

"""

__docformat__ = 'restructuredtext'

import sys

from glob import glob
from collections import Counter
from mock import patch

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.distribution.dataset import Dataset
from ...api import ls
from ...utils import swallow_outputs, chpwd
from ...tests.utils import assert_equal
from ...tests.utils import assert_in
from ...tests.utils import use_cassette
from ...tests.utils import with_tempfile
from ...tests.utils import skip_if_no_network
from ..ls import LsFormatter
from os.path import relpath
from os import mkdir

from datalad.downloaders.tests.utils import get_test_providers


@skip_if_no_network
@use_cassette('test_ls_s3')
def test_ls_s3():
    url = 's3://datalad-test0-versioned/'
    with swallow_outputs():
        # just to skip if no credentials
        get_test_providers(url)

    with swallow_outputs() as cmo:
        res = ls(url)
        assert_equal(len(res), 17)  # all the entries
        counts = Counter(map(lambda x: x.__class__.__name__, res))
        assert_equal(counts, {'Key': 14, 'DeleteMarker': 3})
        assert_in('Bucket info:', cmo.out)
test_ls_s3.tags = ['network']


@with_tempfile
def test_ls_repos(toppath):
    # smoke test pretty much
    GitRepo(toppath + '1', create=True)
    AnnexRepo(toppath + '2', create=True)
    repos = glob(toppath + '*')
    # now make that sibling directory from which we will ls later
    mkdir(toppath)
    def _test(*args_):
        #print args_
        for args in args_:
            for recursive in [False, True]:
                # in both cases shouldn't fail
                with swallow_outputs() as cmo:
                    ls(args, recursive=recursive)
                    assert_equal(len(cmo.out.rstrip().split('\n')), len(args))
                    assert_in('[annex]', cmo.out)
                    assert_in('[git]', cmo.out)
                    assert_in('master', cmo.out)
                    if "bogus" in args:
                        assert_in('unknown', cmo.out)

    _test(repos, repos + ["/some/bogus/file"])
    # check from within a sibling directory with relative paths
    with chpwd(toppath):
        _test([relpath(x, toppath) for x in repos])


@with_tempfile
def test_ls_uninstalled(path):
    ds = Dataset(path)
    ds.create()
    ds.create('sub')
    ds.uninstall('sub', check=False)
    with swallow_outputs() as cmo:
        ls([path], recursive=True)
        assert_in('not installed', cmo.out)


@with_tempfile
def test_ls_noarg(toppath):
    # smoke test pretty much
    AnnexRepo(toppath, create=True)

    # this test is pointless for now and until ls() actually returns
    # something
    with swallow_outputs():
        ls_out = ls(toppath)
        with chpwd(toppath):
            assert_equal(ls_out, ls([]))
            assert_equal(ls_out, ls('.'))


def test_ls_formatter():
    # we will use unicode symbols only when sys.stdio supports UTF-8
    for sysioenc, OK, tty in [(None, "OK", True),
                              ('ascii', 'OK', True),
                              ('UTF-8', u"✓", True),
                              ('UTF-8', "OK", False)]:

        # we cannot overload sys.stdout.encoding
        class fake_stdout(object):
            encoding = sysioenc
            def write(self, *args):
                pass

            def isatty(self):
                return tty

        with patch.object(sys, 'stdout', fake_stdout()):
            formatter = LsFormatter()
            assert_equal(formatter.OK, OK)
            assert_in(OK, formatter.convert_field(True, 'X'))
