# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for handle publishing

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureChoice
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex
from datalad.cmd import CommandError

lgr = logging.getLogger('datalad.interface.POC_publish')


class POCPublish(Interface):
    """publish a handle.

    This is basic implementation for testing purposes
    """

    _params_ = dict(
        dst=Parameter(
            args=('dst',),
            doc="Address to publish the handle to. It's expected to address "
                "the server-side base directory for the published handle. The "
                "published handle repository will be located beneath that "
                "directory.",
            # TODO: really? may be direct git address and derive from there?
            constraints=EnsureStr()),
        src=Parameter(
            args=('src',),
            doc="name of or path to the handle to publish",
            nargs="?",
            constraints=EnsureStr()),
        base_url=Parameter(
            args=('base-url',),
            doc="Public base url of the published handle. This URL is "
                "expected to address the base directory given by 'dst', "
                "meaning that the URL(s) of the published repository(ies) "
                "follow the same hierarchy as the corresponding server-side "
                "directories. Default is 'dst'.",
            # TODO: See above
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        remote_name=Parameter(
            args=('--remote-name',),
            doc="name for the remote to add to the local handle",
            # TODO: default? derived from url
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""If set this also publishes all subhandles of 'src'. Set to
                'list' to publish subhandles at the same directory level as
                the handle itself or set to 'tree' to hierarchically publish
                them.""",
                # TODO: Does 'tree' derive from relative URLs of submodules or
                # from the hierarchy of submodules?
            constraints=EnsureChoice(["tree", "list"])),
        rewrite_urls=Parameter(
            args=("--rewrite-urls", ),
            doc="",
            constraints=EnsureChoice({"ask", "never", "all"}),),)

    def __call__(self, dst, src=curdir, base_url=None, remote_name=None,
                 recursive="list", rewrite_urls="never"):

        # Maybe enhance what dst is expected to be:
        # detect whether dst is a valid git repo => push?
        # => does this imply to not rewrite any URL?
        # => is there a branch to push to?

        # else:
        # detect ssh address
        # => create repo(s) to push to

        # rewrite submodule URLs?
        # => do it locally and push or do it directly on the server?



        return