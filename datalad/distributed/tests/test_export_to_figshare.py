# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test export_to_figshare"""

from datalad.api import (
    Dataset,
    export_archive,
)
from datalad.support import path as op
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    eq_,
    with_tree,
)

from ..export_to_figshare import _get_default_title


@with_tree({})
def test_get_default_title(path=None):
    repo = GitRepo(path)
    ds = Dataset(path)
    # There is no dataset initialized yet, so only path will be the title
    dirname = op.basename(path)
    eq_(_get_default_title(ds), dirname)

    # Initialize and get UUID
    ds.create(force=True)
    eq_(_get_default_title(ds), '{dirname}#{ds.id}'.format(**locals()))

    # Tag and get @version
    # cannot use ds.save since our tags are not annotated,
    # see https://github.com/datalad/datalad/issues/4139
    ds.repo.tag("0.1", message="important version")
    eq_(_get_default_title(ds), '{dirname}#{ds.id}@0.1'.format(**locals()))
