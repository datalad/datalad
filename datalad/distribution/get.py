# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for getting dataset content

"""

import logging

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_get_opts
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import to_options
from datalad.support.exceptions import CommandNotAvailableError

from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import require_dataset

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


class Get(Interface):
    """Get data content for files and/or directories of a dataset.

    Known data locations for each requested file are evaluated and data are
    obtained from the best/fastest/cheapest location, unless a dedicated
    source is identified.

    By default this command operates recursively within a dataset, but not
    across potential subdatasets, i.e. if a directory is provided, all files in
    the directory are obtained. Recursion into subdatasets is supported too. If
    enabled, potential subdatasets are detected and installed sequentially, in
    order to fulfill a request.

    .. note::
      Power-user info: This command used :command:`git annex get` to fulfill
      requests. Subdatasets are obtained via the :func:`~datalad.api.install`
      command.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="PATH",
            doc="""specify the dataset to perform the add operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path/name of the requested dataset component. The component
            must already be known to the dataset.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar="LABEL",
            doc="""label of the data source to be used to fulfill the request.
            This can be the name of a dataset :term:`sibling` or another known
            source""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_get_opts=annex_get_opts)

    @staticmethod
    @datasetmethod(name='get')
    def __call__(
            path=None,
            source=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_get_opts=None):

        ds = require_dataset(dataset, check_installed=True,
                             purpose='getting content')

        # needs to be an annex:
        if not isinstance(ds.repo, AnnexRepo):
            raise CommandNotAvailableError("Missing annex at {0}".format(ds))

        # TODO: path with subdataset? (not recursive => fail)
        # TODO: recursion into subdatasets
        # Note: `path` may be a list, partially within subdatasets ...

        # return value + result renderer

        # Note: general call:
        # ds.repo.get(path, options=['--from="{src}"'.format(src=source)])

        raise NotImplementedError
