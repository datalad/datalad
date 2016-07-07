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

__docformat__ = 'restructuredtext'

import logging
from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import EnsureDataset, datasetmethod
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag, recursion_limit, \
    git_opts, annex_opts, annex_get_opts

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
    @datasetmethod(name='add')
    def __call__(
            dataset=None,
            path=None,
            source=None,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_get_opts=None):
        raise NotImplementedError
