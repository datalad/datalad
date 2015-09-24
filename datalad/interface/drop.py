# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for dropping handle's content
"""

__docformat__ = 'restructuredtext'

from glob import glob
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance

from logging import getLogger
lgr = getLogger('datalad.api.drop')

class Drop(Interface):
    """Drop dataset's content from a remote repository.

    Examples:

      $ datalad drop foo/*
    """

    _params_ = dict(
        paths=Parameter(
            doc="path(s) to data content that is to be dropped.",
            constraints=EnsureStr(),
            metavar='file',
            nargs='+'))

    def __call__(self, paths):

        handle = get_repo_instance(class_=AnnexRepo)

        # 'paths' comes as a list
        # Expansions (like globs) provided by the shell itself are already
        # done. But: We don't know exactly what shells we are running on and
        # what it may provide or not. Therefore, make any expansion we want to
        # guarantee, per item of the list:

        expanded_list = []
        [expanded_list.extend(glob(item)) for item in paths]

        # Figure out how many items were dropped. The easiest/most robust way
        # is probably to check most recent git-annex branch change
        # TODO: migrate into a helper function for proper testing etc
        annex_branches = [b for b in handle.repo.branches if b.name == 'git-annex']
        if not len(annex_branches) == 1:
            raise RuntimeError("There should have been a git-annex branch in %s" % handle.path)
        annex_branch = annex_branches[0]
        # there is no guarantee that annex would record all transactions in a single commit
        # so let's record original state to compare against
        old_hexsha = annex_branch.object.hexsha

        try:
            handle.annex_drop(expanded_list)
        finally:
            # dropping might fail altogether while some files being dropped ok,
            # so report regardless of success or failure
            changed = [d.a_path for d in annex_branch.commit.diff(old_hexsha)
                       if d.a_path.endswith('.log')]
            lgr.info("%d items were dropped" % (len(changed)))

