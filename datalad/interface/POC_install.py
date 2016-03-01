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
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex
from datalad.cmd import CommandError

lgr = logging.getLogger('datalad.interface.POC_install')


class POCInstallHandle(Interface):
    """Install a handle."""

    _params_ = dict(
        src=Parameter(
            doc="url or local path of the handle to install",
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
            constraints=EnsureStr() | EnsureNone()),
        roothandle=Parameter(
            doc="Roothandle, where to install the handle to. Datalad has a "
                "default root handle.",
            constraints=EnsureStr() | EnsureNone()),)

    def __call__(self, src, recursive=False, dest=None, name=None, roothandle=None):
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

        if dest is not None:
            raise NotImplementedError("Option --dest yet to be implemented.")

        # TODO: Enhance functionality (see Note in docstring):
        # check whether 'url' is a locally known name.
        # if so, get a location to clone from.
        # otherwise treat 'path' as an url to clone from
        # if path is None, install to master (checkout the submodule)
        # this means: if the submodule is there already (locally known name),
        # just checkout.

        master = POC_get_root_handle(roothandle)
        lgr.info("Install using root handle '%s' ..." % master.path)

        # if a hierarchical name is given, check whether to install the handle
        # into an existing handle instead of the root handle:
        target_handle = master
        super_handles = list()
        if name is not None and "/" in name:
            for ihandle in get_submodules_list(master):
                if name.startswith(ihandle):
                    super_handles.append(ihandle)

            super_handles.sort(key=len)
            if super_handles:
                # Note: The following call, again, is neither prepared for
                # moved worktrees nor platform independent. Just a POC
                # implementation. ;)
                # TODO: provide something like super_handles[-1].path
                target_handle = GitRepo(opj(master.path, super_handles[-1]))
                # strip prefix from name:
                name = name[len(super_handles[-1]) + 1:]
                lgr.info("Installing into handle '%s' ..." % super_handles[-1])

        # check if a handle with that name already exists:
        # TODO: Decide whether or not we want to check the optional name before
        # even calling "git submodule add" or just wait for its feedback.
        # For now, just catch exception from git call.

        # check, whether 'src' is a local path:
        if exists(src):
            src = abspath(expandvars(expanduser(src)))

        submodules_dict_pre = get_submodules_dict(target_handle)

        # TODO: rollback on exception during git calls? At what point there is
        # anything to roll back?
        # Note: At least the replaced .git-symlink in an annex should be
        # restored on failure. (See below)

        # Workaround for issue, when 'git submodule add' is executed in a
        # submodule conataining an annex. Git then gets confused by annexes
        # .git symlink. Apparently everything is fine, if the .git link is
        # replaced with the standard .git file during 'submodule add'
        # Therefore: Replace it, if it's there and call annex-init again after
        # the submodule was added.
        from os.path import islink
        from os import readlink, remove
        dot_git = opj(target_handle.path, ".git")
        link_target = None
        if islink(dot_git):  # TODO: What happens in direct mode?
            link_target = readlink(dot_git)
            remove(dot_git)
            with open(dot_git, 'w') as f:
                f.write("gitdir: " + link_target)

        try:
            target_handle._git_custom_command('', ["git", "submodule", "add",
                                                   src,
                                                   name if name is not None
                                                   else ''])
        except CommandError as e:
            m = e.stderr.strip()
            # TODO: Is there a better way to evaluate git's message?
            # These strings may change from time to time.
            if m.endswith("' already exists in the index") \
                    and m.startswith("'"):
                raise ValueError("Handle %s already installed." % m[0:-28])
            else:
                raise

        submodules_dict_post = get_submodules_dict(target_handle)

        # check what git added:
        submodules_added_1st_level = [sm for sm in submodules_dict_post
                                      if sm not in submodules_dict_pre]
        dbg_msg = ""
        for sm in submodules_added_1st_level:
            dbg_msg += "Added submodule:\nname: %s\npath: %s\nurl: %s\n" \
                       % (sm, submodules_dict_post[sm]["path"],
                          submodules_dict_post[sm]["url"])
        lgr.debug(dbg_msg)
        assert len(submodules_added_1st_level) == 1

        # evaluate name of added submodule:
        if name is not None:
            assert submodules_added_1st_level[0] == name
        else:
            name = submodules_added_1st_level[0]

        # TODO: init not necessary for just installed top-level handle;
        # recurse into subhandles if --recursive; use git submodule init
        # directly instead of update, since it doesn't require the URL to be
        # available.

        # init and update possible submodule(s):
        std_out = ""
        if recursive:
            just_installed = GitRepo(opj(target_handle.path, name), create=False)
            std_out, std_err = \
                just_installed._git_custom_command('', ["git", "submodule",
                                                        "update", "--init",
                                                        "--recursive"
                                                        if recursive else ''])

        # get list of updated (and initialized) subhandles from output:
        import re
        subhandles = re.findall("Submodule path '(.+?)'", std_out)
        # and sort by length, which gives us simple hierarchy information
        subhandles.sort(key=len)

        # get created hierarchy of submodules of root handle including paths
        # and urls as a nested dict for debug:
        hierarchy = get_submodules_dict(master)
        import json
        lgr.debug("Submodule '%s':\n" % name + str(json.dumps(hierarchy,
                                                              indent=4)))

        # TODO: move worktree if destination is not default

        # commit the changes to target handle (and possibly to further
        # super handles):
        commit_msg = "Installed handle '%s'\n" % name
        for sh in subhandles:
            commit_msg += "Installed subhandle '%s'\n" % sh
        #target_handle.git_commit(commit_msg)
        #  TODO: Why there is an issue with obtaining lock at .git/index.lock
        # when calling commit via GitPython?
        target_handle._git_custom_command('', ["git", "commit", "-m", commit_msg])

        if super_handles:
            super_handles.reverse() # deepest first
            what_to_commit = super_handles[0]  # name of the target handle
            handles_to_commit = super_handles[1:]  # target_handle done already
            # entry for root handle (root handle path + ''):
            if handles_to_commit:
                handles_to_commit.append('')
            else:
                handles_to_commit = ['']

            lgr.debug("Handles to commit: %s" % handles_to_commit)
            from os.path import commonprefix
            for h in handles_to_commit:
                repo = GitRepo(opj(master.path, h), create=False)
                rel_name = what_to_commit[len(commonprefix([what_to_commit, h])):].strip('/')
                lgr.debug("Calling git add/commit '%s' in %s." %
                          (rel_name, repo.path))
                #repo.git_add(rel_name)
                #repo.git_commit(commit_msg)
                # DEBUG: direct calls
                repo._git_custom_command('', ["git", "add", rel_name])
                repo._git_custom_command('', ["git", "commit", "-m", commit_msg])
                what_to_commit = h

        # Workaround: Reinit annex
        if link_target:
            target_handle._git_custom_command('', ["git", "annex", "init"])


        # init annex(es), if any:
        for handle in [name] + subhandles:
            # TODO: This is not prepared for moved worktrees yet:
            handle_path = opj(target_handle.path, handle)
            if is_annex(handle_path):
                lgr.debug("Annex detected in submodule '%s'. "
                          "Calling annex init ..." % handle)
                # Note: The following call might look strange, since init=False
                # is followed by a call of annex_init. This is intentional for
                # the POC implementation.
                AnnexRepo(handle_path, create=False, init=False)._annex_init()

        # final user output
        lgr.info("Successfully installed handle '%s' from %s at %s." %
                 (name, submodules_dict_post[name]["url"],
                  opj(target_handle.path, submodules_dict_post[name]["path"])))
        if subhandles:
            msg = "Included Subhandles:\n"
            for sh in subhandles:
                msg += sh + "\n"
            lgr.info(msg)
