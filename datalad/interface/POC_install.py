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

from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmdline.helpers import POC_get_datalad_master
from .base import Interface
from .POC_helpers import get_submodules, is_annex
from datalad.cmd import CommandError

lgr = logging.getLogger('datalad.interface.POC_install')


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
        dest=Parameter(
            doc="Path where to install the handle. By default this is "
                "path/to/my/datalad/masterhandle/name.",
            constraints=EnsureStr() | EnsureNone()),
        name=Parameter(
            doc="local name of the installed handle. If not provided, it is "
                "derived from the url. Hierarchical names like 'foo/bar' are "
                "supported.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, url, recursive=False, dest=None, name=None):
        """ Simple proof-of-concept implementation for submodule approach.
        Uses just plain git calls.

        Note
        ----
        First implementation just accepts an url and a name and installs
        within master.

        For the proof of concept this implementation avoids the use of
        current GitRepo/AnnexRepo implementation (which aren't prepared for the
        use of submodules), except for direct git (annex) calls.
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
        # TODO: Decide whether or not we want to check the optional name before
        # even calling "git submodule add" or just wait for its feedback.
        # if name in get_submodules(master):
        #     raise ValueError("Handle '%s' already installed." % name)

        if exists(url):
            url = abspath(expandvars(expanduser(url)))

        submodules_pre = get_submodules(master)

        # TODO: rollback on exception during git calls?
        try:
            master._git_custom_command('', ["git", "submodule", "add", url,
                                            name if name is not None else ''])
        except CommandError as e:
            m = e.stderr.strip()
            # TODO: Is there a better way to evaluate git's message?
            # These strings may change from time to time.
            if m.endswith("' already exists in the index") \
                    and m.startswith("'"):
                raise ValueError("Handle %s already installed." % m[0:-28])
            else:
                raise

        submodules_post = get_submodules(master)

        # check what git added:
        submodules_added = [sm for sm in submodules_post
                            if sm not in submodules_pre]
        dbg_msg = ""
        for sm in submodules_added:
            dbg_msg += "Added submodule:\nname: %s\npath: %s\nurl: %s\n" \
                       % (sm, submodules_post[sm]["path"],
                          submodules_post[sm]["url"])
        lgr.debug(dbg_msg)
        assert len(submodules_added) == 1

        # evaluate name of added submodule:
        if name is not None:
            assert submodules_added[0] == name
        else:
            name = submodules_added[0]

        # Note: May be move worktree before init, since init creates the
        # entries in git/config from gitmodules. So we may need to change the
        # gitmodules only.
        # TODO: Test it!

        # init and update the submodule(s):
        std_out, std_err = \
            master._git_custom_command('', ["git", "submodule", "update",
                                            "--init", "--recursive"
                                            if recursive else '', name])

        # get list of updated (and initialized) subhandles from output:
        import re
        subhandles = re.findall("Submodule path '(.+?)'", std_out)
        # and sort by length, which gives us simple hierarchy information
        subhandles.sort(key=len)

        # get created hierarchy of submodules including paths and urls as a
        # nested dict:
        hierarchy = get_submodules(master)[name]
        import json
        lgr.debug("Submodule '%s':\n" % name + str(json.dumps(hierarchy,
                                                              indent=4)))


        # TODO: move worktree if destination is not default:

        # commit the changes to masterhandle:
        commit_msg = "Installed handle '%s'\n" % name
        for sh in subhandles:
            commit_msg += "Installed subhandle '%s'\n" % sh
        master.git_commit(commit_msg)

        # init annex if it is an annex:
        # TODO: Recurse into submodules (This requires a proper representation
        # of submodule hierarchy, which respects possibly moved working trees)

        if is_annex(opj(master.path, submodules_post[name]["path"])):
            lgr.debug("Annex detected in submodule '%s'. Calling annex init ..."
                      % name)
            # Note: The following call might look strange, since init=False is
            # followed by a call of annex_init. This is intentional for the POC
            # implementation.
            AnnexRepo(opj(master.path, submodules_post[name]["path"]),
                      create=False,
                      init=False)._annex_init()

        # final user output
        lgr.info("Successfully installed handle '%s' from %s at %s." %
                 (name, submodules_post[name]["url"],
                  opj(master.path, submodules_post[name]["path"])))
        if subhandles:
            msg = "Included Subhandles:\n"
            for sh in subhandles:
                msg += sh + "\n"
            lgr.info(msg)
