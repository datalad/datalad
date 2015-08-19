# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for getting a handle's content
"""

__docformat__ = 'restructuredtext'

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr


class Get(Interface):
    """Get a dataset from a remote repository

    Examples:

    $ datalad get foo/*
    """

    _params_ = dict(
        path=Parameter(
            doc="path(s) to data content that is to be obtained",
            constraints=EnsureStr(),
            metavar='file',
            nargs='+'))

    def __call__(self, path):
        import glob
        import os
        import os.path

        from datalad.api import Handle
        from datalad.log import lgr

        # Since GitPython doesn't recognize we ar with in a repo, if we are
        # deeper down the tree, walk upwards and look for '.git':
        # TODO: May be provide a patch for GitPython to have it cleaner.
        cwd_before = cwd = os.getcwd()
        while True:
            if os.path.exists(os.path.join(cwd, '.git')):
                break
            else:
                if cwd == '/':  # TODO: Is this platform-dependend?
                    lgr.error("No repository found.")
                    raise ValueError  # TODO: Proper Exception or clean exit?
                else:
                    os.chdir(os.pardir)
                    cwd = os.getcwd()

        ds = Handle(cwd)
        os.chdir(cwd_before)

        # args.path comes as a list
        # Expansions (like globs) provided by the shell itself are already done.
        # But: We don't know exactly what shells we are running on and what it may provide or not.
        # Therefore, make any expansion we want to guarantee, per item of the list:

        expanded_list = []
        for item in path:
            expanded_list.extend(glob.glob(item))
            # TODO: regexp + may be ext. glob zsh-style
            # TODO: what about spaces in filenames and similar things?
            # TODO: os.path.expandvars, os.path.expanduser? Is not needed here, isn't it? Always?

        ds.get(expanded_list)
