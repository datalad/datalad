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
from datalad.interface.common_opts import git_opts, annex_opts, \
    annex_init_opts, dataset_description

lgr = logging.getLogger('datalad.distribution.create')


class Create(Interface):
    """Create a new dataset from scratch.

    This command initializes a new :term:`dataset` at a given location, or the
    current directory. The new dataset can optionally be registered in an
    existing :term:`superdataset` (the new dataset's path needs to be located
    within the superdataset for that, and the superdataset will be detected
    automatically). It is recommended to provide a brief description to label
    the dataset's nature *and* location, e.g. "Michael's music on black
    laptop". This helps humans to identify data locations in distributed
    scenarios.  By default an identifier comprised of user and machine name,
    plus path will be generated.

    Plain Git repositories can be created via the :option:`no-annex` flag.
    However, the result will not be a full dataset, and, consequently, not all
    features are supported (e.g. a description).

    To create a local version of a remote dataset use the
    :func:`~datalad.api.install` command instead.
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""path where the dataset shall be created, directories
            will be created as necessary. If no location is provided, a dataset
            will be created in the current working directory. Either way the
            command will error if the target directory is not empty.""",
            nargs='?',
            # put dataset 2nd to avoid useless conversion
            constraints=EnsureStr() | EnsureDataset() | EnsureNone()),
        description=dataset_description,
        add_to_super=Parameter(
            args=("--add-to-super",),
            doc="""add the created dataset as a component it's super
            dataset, if such exists""",
            action="store_true"),
        no_annex=Parameter(
            args=("--no-annex",),
            doc="""if set, a plain Git repository will be created without any
            annex""",
            action='store_false'),
        annex_version=Parameter(
            args=("--annex-version",),
            doc="""select a particular annex repository version. The
            list of supported versions depends on the available git-annex
            version. This should be left untouched, unless you know what
            you are doing""",
            constraints=EnsureDType(int) | EnsureNone()),
        annex_backend=Parameter(
            args=("--annex-backend",),
            # not listing choices here on purpose to avoid future bugs
            doc="""set default hashing backend used by the new dataset.
            For a list of supported backends see the git-annex
            documentation. The default is optimized for maximum compatibility
            of datasets across platforms (especially those with limited
            path lengths)""",
            nargs=1),
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts,
    )

    @staticmethod
    @datasetmethod(name='create', dataset_argname='path')
    def __call__(
            path=None,
            description=None,
            add_to_super=False,
            no_annex=False,
            annex_version=None,
            annex_backend='MD5E',
            git_opts=None,
            annex_opts=None,
            annex_init_opts=None):
        # if add_to_super:
        #   find parent ds and call its create_subdataset() which calls this
        #   function again, with add_to_super=False and afterwards added the
        #   new subdataset to itself

        if description and no_annex:
            raise ValueError("Incompatible arguments: cannot specify description for "
                             "annex repo and declaring no annex repo.")
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
