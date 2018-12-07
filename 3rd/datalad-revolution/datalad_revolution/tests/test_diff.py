# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad save

"""

__docformat__ = 'restructuredtext'

from datalad.support.exceptions import CommandError

from datalad.tests.utils import (
    with_tempfile,
    create_tree,
    eq_,
    assert_raises,
)

from .. import utils as ut
from ..dataset import RevolutionDataset as Dataset
from datalad.api import (
    rev_save as save,
    rev_create as create,
)
from .utils import (
    assert_repo_status,
)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_diff(path, norepo):
    ds = Dataset(path).rev_create()
    assert_repo_status(ds.path)
    assert_raises(ValueError, ds.repo.diff, fr='WTF', to='MIKE')
    # no diff
    eq_(ds.repo.diff('HEAD', None), {})
    # bogus path makes no difference
    eq_(ds.repo.diff('HEAD', None, paths=['THIS']), {})
    # let's introduce a known change
    create_tree(ds.path, {'new': 'empty'})
    ds.rev_save(to_git=True)
    assert_repo_status(ds.path)
    eq_(ds.repo.diff(fr='HEAD~1', to='HEAD'),
        {ut.Path(ds.repo.pathobj / 'new'): {
            'state': 'added',
            'type': 'file',
            'gitshasum': '7b4d68d70fcae134d5348f5e118f5e9c9d3f05f6'}})
    # modify known file
    create_tree(ds.path, {'new': 'notempty'})
    eq_(ds.repo.diff(fr='HEAD', to=None),
        {ut.Path(ds.repo.pathobj / 'new'): {
            'state': 'modified',
            'type': 'file'}})
    # per path query gives the same result
    eq_(ds.repo.diff(fr='HEAD', to=None),
        ds.repo.diff(fr='HEAD', to=None, paths=['new']))
    # also given a directory as a constraint does the same
    eq_(ds.repo.diff(fr='HEAD', to=None),
        ds.repo.diff(fr='HEAD', to=None, paths=['.']))
    # but if we give another path, it doesn't show up
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['other']), {})

    # make clean
    ds.rev_save()
    assert_repo_status(ds.path)

    # untracked stuff
    create_tree(ds.path, {'deep': {'down': 'untracked', 'down2': 'tobeadded'}})
    # default is to report all files
    eq_(ds.repo.diff(fr='HEAD', to=None),
        {
            ut.Path(ds.repo.pathobj / 'deep' / 'down'): {
                'state': 'untracked',
                'type': 'file'},
            ut.Path(ds.repo.pathobj / 'deep' / 'down2'): {
                'state': 'untracked',
                'type': 'file'}})
    # but can be made more compact
    eq_(ds.repo.diff(fr='HEAD', to=None, untracked='normal'),
        {
            ut.Path(ds.repo.pathobj / 'deep'): {
                'state': 'untracked',
                'type': 'directory'}})

    # again a unmatching path constrainted will give an empty report
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['other']), {})
    # perfect match and anything underneath will do
    eq_(ds.repo.diff(fr='HEAD', to=None, paths=['deep']),
        {
            ut.Path(ds.repo.pathobj / 'deep' / 'down'): {
                'state': 'untracked',
                'type': 'file'},
            ut.Path(ds.repo.pathobj / 'deep' / 'down2'): {
                'state': 'untracked',
                'type': 'file'}})
