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


from os.path import join as opj
from datalad.support.gitrepo import GitRepo, InvalidGitRepositoryError


def get_submodules(repo):
    """

    :param repo: GitRepo
    :return: dict
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
            submodules[name]["submodules"] = get_submodules(rec_repo)
        except InvalidGitRepositoryError:
            # non initialized submodule is invalid repo, so no information
            # about further submodules
            submodules[name]["submodules"] = {}
    return submodules


def get_module_parser(repo):

    from git import GitConfigParser
    parser = GitConfigParser(opj(repo.path, ".gitmodules"))
    parser.read()
    return parser


def is_annex(path):
    from datalad.support.gitrepo import GitRepo
    repo = GitRepo(path, create=False)
    return "origin/git-annex" in repo.git_get_remote_branches()

