# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for modifying URLs of subhandles

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, \
    EnsureDatasetAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.cmdline.helpers import POC_get_root_handle
from datalad.interface.base import Interface
from datalad.distribution.dataset import Dataset, EnsureDataset, datasetmethod
from datalad.interface.POC_helpers import get_submodules_dict, get_submodules_list, get_all_submodules_dict, get_git_dir, get_module_parser
from datalad.cmd import CommandError
from datalad.utils import assure_dir
from datalad.consts import HANDLE_META_DIR, POC_STD_META_FILE

lgr = logging.getLogger('datalad.distribution.modify_subhandle_urls')


class ModifySubhandleURLs(Interface):
    """Modify the URLs of subdatasets of a dataset."""

    _params_ = dict(
        url=Parameter(
            args=("url",),
            doc="A template for building the URLs of the subhandles."
                "List of currently available placeholders:\n"
                "%NAME\tthe name of the handle, where slashes are replaced by "
                "dashes.",
            constraints=EnsureStr()),
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc=""""specify the dataset to update. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="Recursively modify all subhandle URLs of `dataset`."),)

    # TODO: User interaction. Allow for skipping and editing on a per
    # subhandle basis. Therefore some --mode option (see below). Additionally,
    # this leads to URL being optional, so no URL given means to
    # edit per subhandle
    # mode=Parameter(
    #     args=("--mode",),
    #     doc="",
    #     constraints=EnsureChoice(["all", "ask"]),)

    @staticmethod
    @datasetmethod(name='modify_subhandle_urls')
    def __call__(url, dataset=None, recursive=False):

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        # if we have no dataset given, figure out which one we need to operate
        # on, based on the current working directory of the process:
        if ds is None:
            # try to find a dataset at or above PWD:
            dspath = GitRepo.get_toppath(getpwd())
            if dspath is None:
                raise ValueError("No dataset found at %s." % getpwd())
            ds = Dataset(dspath)
        assert(ds is not None)

        if not ds.is_installed():
            raise ValueError("No installed dataset found at "
                             "{0}.".format(ds.path))
        assert(ds.repo is not None)

        repos_to_update = [ds.repo]
        if recursive:
            repos_to_update += [GitRepo(opj(ds.path, sub_path))
                                for sub_path in
                                ds.get_dataset_handles(recursive=True)]

        for handle_repo in repos_to_update:
            parser = get_module_parser(handle_repo)
            for submodule_section in parser.sections():
                submodule_name = submodule_section[11:-1]
                parser.set_value(submodule_section, "url",
                                 url.replace("%NAME",
                                             submodule_name.replace("/", "-")))

        return  # TODO: return value?
