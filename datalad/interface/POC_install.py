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
from datalad.cmd import Runner
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex, get_all_submodules_dict, get_git_dir
from datalad.cmd import CommandError
from datalad.utils import assure_dir
from datalad.consts import HANDLE_META_DIR, POC_STD_META_FILE

lgr = logging.getLogger('datalad.interface.POC_install')


class POCInstallHandle(Interface):
    """Install a handle."""

    _params_ = dict(
        src=Parameter(
            args=("src",),
            doc="url or local path of the handle to install",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        dest=Parameter(
            args=("dest",),
            doc="Path where to install the handle. By default this is "
                "path/to/my/datalad/masterhandle/name.",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""If set this installs all possibly existing subhandles,
             too."""),
        name=Parameter(
            doc="local name of the installed handle. If not provided, it is "
                "derived from the url. Hierarchical names like 'foo/bar' are "
                "supported.",
            constraints=EnsureStr() | EnsureNone()),
        roothandle=Parameter(
            doc="Roothandle, where to install the handle to. Datalad has a "
                "default root handle.",
            constraints=EnsureStr() | EnsureNone()),
        create=Parameter(
            args=("--create",),
            doc="Create a handle.",
            action="store_true",),)

    def __call__(self, src=None, dest=None, recursive=False, name=None,
                 roothandle=None, create=False):
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

        # TODO: Allow for passing customized Runners/protocols
        runner = Runner()

        # TODO: Use 'dest' internally in order to prepare the code for whatever
        # kind of implementation of moved worktrees or similar independency of
        # name and path of a submodule.

        # TODO: Adapt path manipulation and translation name <-> path
        # (cross-platform)"

        # Note: 'dest' without '--name' currently leads to a clone, that is not
        # installed as a submodule into any roothandle. Therefore it may be
        # seen as a root handle.
        # TODO: doc
        lgr.debug("Options:\nsrc: {s}\ndest: {d}\nrecursive: {r}\nname: {n}\n"
                  "roothandle:{rt}\ncreate: {c}".format(s=src, d=dest,
                                                        r=recursive, n=name,
                                                        rt=roothandle, c=create))
        if dest is not None:
            if name is not None:
                raise NotImplementedError("Paramaters 'dest' and '--name' "
                                          "combined are implying the use of "
                                          "'git worktree'.\n"
                                          "Not implemented yet.")
            if exists(dest):
                # create a root handle
                target_repo = GitRepo(dest, src, create=True)
                if is_annex(dest):
                    target_repo._git_custom_command('', ["git", "annex", "init"])
                lgr.info("Installation succesfull.")
                return
            else:
                raise ValueError("'%s' does not exist." % dest)

        master = POC_get_root_handle(roothandle)
        # XXX this implies git submodule status --recursive and can get slow
        # even with 100 subhandles.
        known_handles = get_all_submodules_dict(master.path)
        lgr.info("Install using root handle '%s' ..." % master.path)

        if src is not None:
            src_as_name = src.rstrip('/')
        if name is not None:
            name = name.rstrip('/')
        # Note: To strip os.sep instead of '/' seems to not be reasonable,
        # since we are trying to treat src as a (datalad defined) name, that
        # allows for '/' only. If there is os.sep like '\', src obviously is a
        # path not a name!

        # Note: For now, "create" is separate thing. Should eventually be
        # melted in.
        if create:

            if name is None:
                raise ValueError("--name is required with --create.")
            if name in known_handles:
                raise ValueError("Handle '%s' already exists." % name)

            # figure out, where to install it (what's the superhandle to add
            # it as a submodule to?):
            install_path = opj(master.path, name)

            # TODO: what to do if install_path exists already? No 'official'
            # decision yet.
            # Currently: just let git init decide.
            # TODO: create the dir in case it doesn't exist yet?
            # Currently: yes.
            assure_dir(install_path)

            candidates = [h for h in known_handles
                          if name.startswith('%s/' % h) and h != name]
            # if there is none, the only super handle is the roothandle,
            # otherwise the longest prefix is the interesting one:
            if len(candidates) > 0:
                candidates.sort(key=len)
                rel_src_name = name[len(candidates[-1]):]
                super_handle_path = opj(master.path, candidates[-1])
            else:
                rel_src_name = name
                super_handle_path = master.path

            # create the repo:
            cmd_list = ["git", "init"]
            runner.run(cmd_list, cwd=install_path)

            # create initial commit:
            assure_dir(opj(install_path, HANDLE_META_DIR))
            with open(opj(install_path, HANDLE_META_DIR, "metadata"), "w") as f:
                f.write("\n")
            cmd_list = ["git", "add", opj(".", HANDLE_META_DIR, POC_STD_META_FILE)]
            runner.run(cmd_list, cwd=install_path)
            cmd_list = ["git", "commit", "-m", "\"Initial commit.\""]
            runner.run(cmd_list, cwd=install_path)

            # add it as a submodule to its superhandle:
            cmd_list = ["git", "submodule", "add", "./" + rel_src_name]
            runner.run(cmd_list, cwd=super_handle_path)

            # move .git to superrepo's .git/modules, remove .git, create
            # .git-file
            installed_handle_git_dir = opj(install_path, ".git")
            super_handle_git_dir = get_git_dir(super_handle_path)
            moved_git_dir = opj(super_handle_path, super_handle_git_dir,
                                "modules", rel_src_name)
            assure_dir(moved_git_dir)
            from os import rename, listdir, rmdir
            for dot_git_entry in listdir(installed_handle_git_dir):
                rename(opj(installed_handle_git_dir, dot_git_entry),
                       opj(moved_git_dir, dot_git_entry))
            assert not listdir(installed_handle_git_dir)
            rmdir(installed_handle_git_dir)

            with open(opj(install_path, ".git"), "w") as f:
                f.write("gitdir: {moved}\n".format(moved=moved_git_dir))

            # commit submodule addition (recurse upwards)
            cmd_list = ["git", "commit", "-m", "Added handle %s" % rel_src_name]
            if super_handle_path != master.path:
                for i in range(1, len(candidates)):
                    runner.run(cmd_list, cwd=opj(master.path, candidates[-i]))
            else:
                runner.run(cmd_list, cwd=super_handle_path)

            return

        # figure out, what to install:
        # 1. is src an already known handle?
        elif src_as_name in known_handles:
            # already installed?
            if known_handles[src_as_name]["initialized"]:
                raise ValueError("Handle '%s' already installed." % src_as_name)

            # TODO: Currently options like 'name', 'create' or 'dest' are
            # ignored in this case. Decide how to treat them.

            # get its super handle:
            candidates = [h for h in known_handles
                          if src_as_name.startswith(h) and h != src_as_name]
            # if there is none, the only super handle is the roothandle,
            # otherwise the longest prefix is the interesting one:
            if len(candidates) > 0:
                candidates.sort(key=len)
                rel_src_name = src_as_name[len(candidates[-1]):].strip("/")
                super_handle_path = opj(master.path, candidates[-1])
            else:
                rel_src_name = src_as_name
                super_handle_path = master.path

            if name:
                lgr.warning("option --name currently ignored in case of an "
                            "already known handle")

            # install it:
            cmd_list = ["git", "submodule", "update", "--init"]
            if recursive:
                cmd_list.append("--recursive")
            cmd_list.append(rel_src_name)
            runner.run(cmd_list, cwd=super_handle_path)

            # TODO: annex init recursively! => Move to bottom; that's post
            # install stuff!
            if is_annex(opj(super_handle_path, rel_src_name)):
                lgr.debug("Annex detected in submodule '%s'. "
                          "Calling annex init ..." % name)
                cmd_list = ["git", "annex", "init"]
                runner.run(cmd_list, cwd=super_handle_path)
            return

        # 2. check, whether 'src' is a local path or valid url:
        # Currently just assume it's one of both. Check implicit.
        else:
            if exists(src):
                src = abspath(expandvars(expanduser(src)))

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

        # else:
        #
        #     raise ValueError("Unknown source for installation: %s" % src)
