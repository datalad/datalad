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


from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.cmdline.helpers import POC_get_datalad_master
from .base import Interface
from .POC_helpers import get_submodules


class POCInstallHandle(Interface):
    """Install a handle."""

    _params_ = dict(
        url=Parameter(
            doc="url of the handle to install",
            constraints=EnsureStr()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""If set this installs all possibly existing subhandles,
             too."""),
        name=Parameter(
            doc="local name of the installed handle. If not provided, it is "
                "derived from the url. Hierarchical names like 'foo/bar' are "
                "supported.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, url, recursive=False, name=None):
        """ Simple proof-of-concept implementation for submodule approach.
        Uses just plain git calls.

        Note
        ----
        First implementation just accepts an url and a name and installs
        within master.
        """

        # TODO: Enhance functionality (see Note in docstring):
        # check whether 'path' is a locally known name.
        # if so, get a location to clone from.
        # otherwise treat 'path' as an url to clone from
        # if path is None, install to master (checkout the submodule)
        # this means: if the submodule is there already (locally known name),
        # just checkout.

        master = POC_get_datalad_master()

        # check if a handle with that name already exists:
        if name in get_submodules(master):
            raise ValueError("Handle '%s' already installed." % name)

        if exists(url):
            url = abspath(expandvars(expanduser(url)))

        # TODO: rollback on exception during git calls?
        master._git_custom_command('', ["git", "submodule", "add", url, name])
        master._git_custom_command('', ["git", "submodule", "update", "--init",
                                        "--recursive" if recursive else '',
                                        name])

        # TODO: msg should also list installed subhandles!
        master.git_commit("Installed handle '%s'" % name)




