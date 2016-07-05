# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding dataset components

"""

__docformat__ = 'restructuredtext'

import logging
from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import EnsureDataset, datasetmethod
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag, recursion_limit, \
    git_opts, annex_opts, annex_add_opts

lgr = logging.getLogger('datalad.distribution.add')


class Add(Interface):
    """Add files/directories to an existing dataset.

    Typically, files and directories to be added to a dataset would be placed
    into a directory of a dataset, and subsequently this command can be used to
    register this new content with the dataset. With recursion enabled,
    files will be added to their respective subdatasets as well.

    Alternatively, a source location can be given to indicate where to obtain
    data from. If no `path` argument is provided in this case, the content will
    be obtained from the source location and a default local name, derived from
    the source location will be generated. Alternatively, an explicit `path`
    can be given to override the default.

    If more than one `path` argument and a source location are provided, the
    `path` arguments will be sequentially used to complete the source URL/path
    (be means of concatenation), and an attempt is made to obtain data from
    those locations.


    || REFLOW >>
    By default all files are added to the dataset's :term:`annex`, i.e. only
    their content identity and availability information is tracked with Git.
    This results in lightweight datasets. If desired, the [PY: `to_git`
    PY][CMD: --to-git CMD] flag can be used to tell datalad to inject files
    directly into Git. While this is not recommended for binary data or large
    files, it can be used for source code and meta-data to be able to benefit
    from Git's track and merge capabilities. Files checked directly into Git
    are always and unconditionally available immediately after installation of
    a dataset.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git annex add`, :command:`git annex addurl`, or
      :command:`git add` to incorporate new dataset content.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to perform the add operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name of the component to be added. The component
            must either exist on the filesystem already, or a `source`
            has to be provided.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar='URL/PATH',
            doc="url or local path of the to be added component's source",
            constraints=EnsureStr() | EnsureNone()),
        to_git=Parameter(
            args=("--to-git",),
            action='store_true',
            doc="""flag whether to add data directly to Git, instead of
            tracking data identity only.  Usually this is not desired,
            as it inflates dataset sizes and impacts flexibility of data
            transport"""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_add_opts=annex_add_opts)

    @staticmethod
    @datasetmethod(name='add')
    def __call__(
            dataset=None,
            path=None,
            source=None,
            to_git=False,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None):
        raise NotImplementedError
