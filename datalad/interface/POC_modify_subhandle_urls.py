# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for handle installation

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, \
    EnsureHandleAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex, get_all_submodules_dict, get_git_dir, get_module_parser
from datalad.cmd import CommandError
from datalad.utils import assure_dir
from datalad.consts import HANDLE_META_DIR, POC_STD_META_FILE

lgr = logging.getLogger('datalad.interface.POC_install')


class POCModifySubhandleURLs(Interface):
    """Install a handle."""

    _params_ = dict(
        url=Parameter(
            args=("url",),
            doc="A template for building the URLs of the subhandles."
                "List of currently available placeholders:\n"
                "%%NAME\tthe name of the handle, where slashes are replaced by "
                "dashes.",
            constraints=EnsureStr()),
        handle=Parameter(
            args=('--handle',),
            doc="Name of or path to the handle, whose subhandle URLs to modify. "
                "Defaults to CWD.",
            nargs="?",
            constraints=EnsureHandleAbsolutePath()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="Recursively modify all subhandle URLs of HANDLE."),)

    # TODO: User interaction. Allow for skipping and editing on a per
    # subhandle basis. Therefore some --mode option (see below). Additionally,
    # this leads to URL being optional, so no URL given means: Edit per subhandle
    # mode=Parameter(
    #     args=("--mode",),
    #     doc="",
    #     constraints=EnsureChoice(["all", "ask"]),)

    def __call__(self, url, handle=curdir, recursive=False):

        # TODO: Exception handling:
        top_handle_repo = GitRepo(handle, create=False)

        handles_to_update = [top_handle_repo]
        if recursive:
            handles_to_update += [GitRepo(opj(top_handle_repo.path, sub_path))
                                  for sub_path in
                                  get_submodules_list(top_handle_repo)]

        for handle_repo in handles_to_update:
            parser = get_module_parser(handle_repo)
            for submodule_section in parser.sections():
                submodule_name = submodule_section[11:-1]
                parser.set_value(submodule_section, "url",
                                 url.replace("%%NAME",
                                             submodule_name.replace("/", "-")))

        return
