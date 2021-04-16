# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test no_annex"""


from os.path import join as opj
from datalad.api import (
    create,
    no_annex,
)
from datalad.utils import Path
from datalad.tests.utils import (
    assert_repo_status,
    create_tree,
    eq_,
    known_failure_githubci_win,
    with_tempfile,
)


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_no_annex(path):
    ds = create(path)
    assert_repo_status(ds.path)
    create_tree(
        ds.path,
        {'code': {
            'inannex': 'content',
            'notinannex': 'othercontent'},
         'README': 'please'})
    # add inannex pre configuration
    ds.save(opj('code', 'inannex'))
    no_annex(pattern=['code/**', 'README'], dataset=ds.path)
    # add inannex and README post configuration
    ds.save([opj('code', 'notinannex'), 'README'])
    assert_repo_status(ds.path)
    # one is annex'ed, the other is not, despite no change in add call
    # importantly, also .gitattribute is not annexed
    eq_([opj('code', 'inannex')],
        [str(Path(p)) for p in ds.repo.get_annexed_files()])
