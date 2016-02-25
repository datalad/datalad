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


def get_submodules(repo):
    """

    :param repo: GitRepo
    :return: list
    """
    # TODO: May be check for more than just being represented in GitPython.
    # Figure out, what the presence of a submodule therein actually implies.
    return [sm.name for sm in repo.repo.submodules]