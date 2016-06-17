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
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureDType
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo

lgr = logging.getLogger('datalad.distribution.create')


class Create(Interface):
    """Create a new dataset.

    This command initializes a new repository at a given location, or the
    current directory.
    """

    _params_ = dict(
        loc=Parameter(
            args=("loc",),
            doc="""location where the dataset shall be  created.  If `None`,
            is given a dataset will be created in the current working
            directory""",
            nargs='?',
            # put dataset 2nd to avoid useless conversion
            constraints=EnsureStr() | EnsureDataset() | EnsureNone()),
        description=Parameter(
            args=("-D", "--description",),
            doc="""short description that humans can use to identify the
            repository/location, e.g. "Precious data on my laptop.""""",
            nargs=1),
        no_annex=Parameter(
            args=("--no-annex",),
            doc="""flag that if given a plain Git repository will be created
            without any annex""",
            action='store_false'),
        annex_version=Parameter(
            args=("--annex-version",),
            doc="""select particular annex repository version.  The list of
            supported versions depends on the available git-annex version""",
            constraints=EnsureDType(int) | EnsureNone()),
        annex_backend=Parameter(
            args=("--annex-backend",),
            # not listing choices here on purpose to avoid future bugs
            doc="""set default hashing backend used by the new dataset.
            For a list of supported backends see the git-annex
            documentation""",
            nargs=1),
    )

    @staticmethod
    @datasetmethod(name='create', dataset_argname='loc')
    def __call__(
            loc=None, description=None, no_annex=False, annex_version=None,
            annex_backend='MD5E'):
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
            vcs = AnnexRepo(
                loc, url=None, create=True, backend=annex_backend,
                version=annex_version, description=description)
        return Dataset(loc)
