# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a proxy to git annex unlock

"""

__docformat__ = 'restructuredtext'

import logging
from os.path import commonprefix
from os.path import abspath

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.utils import getpwd

from .base import Interface

lgr = logging.getLogger('datalad.interface.unlock')


class Unlock(Interface):
    """Unlock file(s) of a dataset

    Unlock files of a dataset in order to be able to edit the actual content
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""file(s) to unlock""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to unlock files in. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If the latter fails, an
            attempt is made to identify the dataset based on `path` """,
            constraints=EnsureDataset() | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='unlock')
    def __call__(path=None, dataset=None):
        # shortcut
        ds = dataset

        if isinstance(path, list):
            if not len(path):
                # normalize value to expected state when nothing was provided
                path = None
            elif len(path) == 1:
                # we can simply continue with the function as called with a
                # single argument
                path = path[0]

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if ds is None:
            # try CWD:
            dspath = GitRepo.get_toppath(getpwd())
            if not dspath:
                if path is None:
                    raise InsufficientArgumentsError(
                        "insufficient arguments for unlocking: needs at least "
                        "a dataset or a path to unlock.")
                # if we still have no dataset, try deriving it from path(s):
                if isinstance(path, list):
                    # several paths and no dataset given;
                    # paths have to be absolute and have to have common prefix
                    # in order to be able to find a dataset

                    # TODO: maybe consider realpath?
                    prefix = commonprefix(path)
                    if not prefix:
                        raise InsufficientArgumentsError(
                            "insufficient information for unlocking: no "
                            "dataset given and paths don't have a common base "
                            "to check for a dataset")
                    dspath = GitRepo.get_toppath(abspath(prefix))
                else:
                    # single path
                    dspath = GitRepo.get_toppath(abspath(path))

            if dspath is None:
                raise InsufficientArgumentsError(
                    "insufficient information for unlocking: no "
                    "dataset given and none could be derived "
                    "from given path(s) or current working directory")

            ds = Dataset(dspath)

        assert ds
        assert ds.repo

        if not isinstance(ds.repo, AnnexRepo):
            # TODO: Introduce NoAnnexError
            raise ValueError("No annex found in dataset (%s)." % ds.path)

        # TODO: AnnexRepo().unlock() with proper return value
        if not path:
            files = []
        elif isinstance(path, list):
            files = path
        else:
            files = [path]

        std_out, std_err = ds.repo._annex_custom_command(
            files, ['git', 'annex', 'unlock'])

        return [line.split()[1] for line in std_out.splitlines()
                if line.strip().endswith('ok')]

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was unlocked")
            return
        items = '\n'.join(map(str, res))
        msg = "Unlocked {n} files:\n{items}".format(
            n=len(res),
            items=items)
        ui.message(msg)
