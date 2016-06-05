# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset creation

"""

__docformat__ = 'restructuredtext'

import logging
import os
from datalad.distribution.dataset import Dataset, datasetmethod, EnsureDataset
from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo

lgr = logging.getLogger('datalad.distribution.create')


class Create(Interface):
    """Create a new dataset.

    """

    _params_ = dict(
        loc=Parameter(
            args=("loc",),
            doc="""location where the dataset shall be  created. If `None`,
            a dataset will be created in the current working directory.""",
            nargs='?',
            # put dataset 2nd to avoid useless conversion
            constraints=EnsureStr() | EnsureDataset() | EnsureNone()),
        no_annex=Parameter(
            args=("--no-annex",),
            doc="""Flag that if given a plain Git repository will be created
            without any annex.""",
            action='store_false'))

    @staticmethod
    @datasetmethod(name='create', dataset_argname='loc')
    def __call__(loc=None, no_annex=False):
        if loc is None:
            loc = os.curdir
        elif isinstance(loc, Dataset):
            loc = loc.path
        if no_annex:
            lgr.info("Creating a new git repo at %s", loc)
            vcs = GitRepo(loc, url=None, create=True)
        else:
            # always come with annex when created from scratch
            lgr.info("Creating a new annex repo at %s", loc)
            vcs = AnnexRepo(loc, url=None, create=True)
        return Dataset(loc)
