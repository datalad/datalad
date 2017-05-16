# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the base of our custom remotes"""

from os.path import isabs

from datalad.tests.utils import with_tree
from datalad.support.annexrepo import AnnexRepo

from ..base import AnnexCustomRemote


@with_tree(tree={'file.dat': ''})
def test_get_contentlocation(tdir):
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.add('file.dat')
    repo.commit('added file.dat')

    key = repo.get_file_key('file.dat')
    cr = AnnexCustomRemote(tdir)
    key_path = cr.get_contentlocation(key, absolute=False)
    assert not isabs(key_path)
    key_path_abs = cr.get_contentlocation(key, absolute=True)
    assert isabs(key_path_abs)
    assert cr._contentlocations == {key: key_path}
    repo.drop('file.dat', options=['--force'])
    assert not cr.get_contentlocation(key, absolute=True)
