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


def get_module_parser(repo):

    from git import GitConfigParser
    gitmodule_path = opj(repo.path, ".gitmodules")
    # TODO: What does constructor of GitConfigParser, in case file doesn't exist?
    #if exists(gitmodule_path):
    parser = GitConfigParser(gitmodule_path)
    parser.read()
    return parser


def get_config_parser(repo):

    from git import GitConfigParser
    git_config_path = opj(repo.path, get_git_dir(repo.path), "config")
    # TODO: What does constructor of GitConfigParser, in case file doesn't exist?
    parser = GitConfigParser(git_config_path)
    parser.read()
    return parser


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
