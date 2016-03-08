# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for POC commands. Functions from this file will most likely be
melted in class hierarchy during refactoring for 'real' implementation of
these commands.
"""

__docformat__ = 'restructuredtext'


from os.path import join as opj, abspath, expanduser, expandvars
from datalad.support.gitrepo import GitRepo, InvalidGitRepositoryError
from datalad.cmd import Runner


def get_all_submodules_dict(path, runner=None):

    if runner is None:
        runner = Runner()

    submodules = dict()

    cmd_list = ["git", "submodule", "status", "--recursive"]
    out, err = runner.run(cmd_list, cwd=abspath(expanduser(expandvars(path))))
    lines = [line.split() for line in out.splitlines()]
    for line in lines:
        submodules[line[1]] = dict()
        submodules[line[1]]["initialized"] = not line[0].startswith('-')
        submodules[line[1]]["modified"] = line[0].startswith('+')
        submodules[line[1]]["conflict"] = line[0].startswith('U')

    # TODO: recurse .gitmodules to read URLs?

    return submodules


def get_submodules_dict(repo):
    """ Get a simple hierarchical representation of the initialized submodules
    of a git repository.

    Parameter
    ---------
    repo: GitRepo

    Returns
    -------
    dict
    """

    parser = get_module_parser(repo)
    submodules = dict()
    for entry in parser.sections():
        name = entry[11:-1]
        submodules[name] = dict()
        submodules[name]["path"] = parser.get_value(entry, "path")
        submodules[name]["url"] = parser.get_value(entry, "url")
        try:
            rec_repo = GitRepo(opj(repo.path, submodules[name]["path"]), create=False)
            submodules[name]["submodules"] = get_submodules_dict(rec_repo)
        except InvalidGitRepositoryError:
            # non initialized submodule is invalid repo, so no information
            # about further submodules
            submodules[name]["submodules"] = {}
    return submodules


def get_submodules_list(repo):
    """Get a list of checked out submodules in a git repository.

    Parameter
    ---------
    repo: GitRepo

    Returns
    -------
    list of str
    """

    out, err = repo._git_custom_command('', ["git", "submodule", "foreach", "--recursive"])
    submodules = list()
    for line in out.splitlines():
        if line.startswith("Entering"):
            submodules.append(line.split()[1].strip("'"))
    return submodules


def get_module_parser(repo):

    from git import GitConfigParser
    from os.path import exists
    gitmodule_path = opj(repo.path, ".gitmodules")
    # TODO: What does constructor of GitConfigParser, in case file doesn't exist?
    #if exists(gitmodule_path):
    parser = GitConfigParser(gitmodule_path)
    parser.read()
    return parser


def get_config_parser(repo):

    from git import GitConfigParser
    from os.path import exists
    git_config_path = opj(repo.path, get_git_dir(repo.path), "config")
    # TODO: What does constructor of GitConfigParser, in case file doesn't exist?
    parser = GitConfigParser(git_config_path)
    parser.read()
    return parser


def is_annex(path):
    from os.path import exists
    if not exists(path):
        return False
    from datalad.support.gitrepo import GitRepo
    repo = GitRepo(path, create=False)
    return "origin/git-annex" in repo.git_get_remote_branches() or "git-annex" in repo.git_get_branches()


def get_git_dir(path):
    """figure out a repo's gitdir

    '.git' might be a  directory, a symlink or a file

    Parameter
    ---------
    path: str
      currently expected to be the repos base dir

    Returns
    -------
    str
      relative path to the repo's git dir; So, default would be ".git"
    """

    from os.path import exists, islink, isdir, isfile
    from os import readlink

    dot_git = opj(path, ".git")
    if not exists(dot_git):
        raise RuntimeError("Missing .git in %s." % path)
    elif islink(dot_git):
        git_dir = readlink(dot_git)
    elif isdir(dot_git):
        git_dir = ".git"
    elif isfile(dot_git):
        with open(dot_git) as f:
            git_dir = f.readline().lstrip("gitdir:").strip()

    return git_dir


def get_remotes(repo, all=False):
    """get git remotes.

    Parameter
    ---------
    all: bool
      if False, ignore any remote, that has an option, starting with "annex" in
      its git config file
    """

    all_remotes = repo.git_get_remotes()

    if all:
        return all_remotes
    else:
        parser = get_config_parser(repo)
        ignore = list()
        for remote in all_remotes:
            items = parser.items("remote \"" + remote + "\"")
            for item in items:
                if item[0].startswith("annex"):
                    ignore.append(remote)
                    break
        return [remote for remote in all_remotes if remote not in ignore]
