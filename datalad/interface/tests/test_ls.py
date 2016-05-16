# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
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

from glob import glob

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from ...api import ls
from ...utils import swallow_outputs
from ...tests.utils import assert_equal, assert_in
from ...tests.utils import use_cassette
from ...tests.utils import with_tempfile

from datalad.downloaders.tests.utils import get_test_providers


@use_cassette('test_ls_s3')
def test_ls_s3():
    url = 's3://datalad-test0-versioned/'
    with swallow_outputs():
        # just to skip if no credentials
        get_test_providers(url)

    with swallow_outputs() as cmo:
        assert_equal(ls(url), None)  # not output ATM
        assert_in('Bucket info:', cmo.out)
test_ls_s3.tags = ['network']


@with_tempfile
def test_ls_repos(toppath):
    # smoke test pretty much
    GitRepo(toppath + '1', create=True)
    AnnexRepo(toppath + '2', create=True)
    repos = glob(toppath + '*')

    for args in (repos, repos + ["bogus"]):
        # in both cases shouldn't fail
        with swallow_outputs() as cmo:
            ls(args)
            assert_equal(len(cmo.out.rstrip().split('\n')), len(args))
            assert_in('[annex]', cmo.out)
            assert_in('[git]', cmo.out)
            assert_in('master', cmo.out)
            if "bogus" in args:
                assert_in('unknown', cmo.out)