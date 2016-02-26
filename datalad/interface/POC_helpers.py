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


def get_submodules(repo):
    """

    :param repo: GitRepo
    :return: list
    """
    # TODO: May be check for more than just being represented in GitPython.
    # Figure out, what the presence of a submodule therein actually implies.
    # return [sm.name for sm in repo.repo.submodules]

    parser = get_module_parser(repo)
    submodules = dict()
    for entry in parser.sections():
        submodules[entry[11:-1]] = dict()
        submodules[entry[11:-1]]["path"] = parser.get_value(entry, "path")
        submodules[entry[11:-1]]["url"] = parser.get_value(entry, "url")
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

