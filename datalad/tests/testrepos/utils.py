# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utilities for test repositories
"""


import os
from os.path import join as opj
import tempfile

from .. import _TEMP_PATHS_GENERATED
from ..utils import get_tempfile_kwargs
from ...utils import better_wraps
from ...utils import optional_args
from .repos import *


# TODO: - use the power!
#       - Items themselves represent a SHOULD-BE state of things. If we don't
#         call create(), they simply define what to test for and we can still
#         call assert_intact to test the state on FS against this definition.
#       - Our actual tests could instantiate indepedent Items (without creating
#         them!) to represent intended changes and then just call assert_intact
#         to test for everything without the need to think of everything when
#         writing the test.
#       - That way, we can have helper functions for such assertions like:
#         take that file from the TestRepo and those changes I specified and
#         test, whether or not those changes and those changes only actually
#         apply. This would just copy the Item from TestRepo, inject the changes
#         and call assert_intact() without ever calling create()



# TODO: can we stack with_testrepos_new in order to set read_only for just some of it? (for example: everything without a submodule can be read_only, since we want to just notice that fact and fail accordingly. More test code is then to be executed for the ones that have submodules only)

@optional_args
def with_testrepos_new(t, read_only=False, selector='all'):
    # selector: regex again?
    # based on class names or name/keyword strings instead?
    # -> May be have TestRepo properties (ItemSelf respectively) like
    #    `is_annex`, `has_submodules`, ... and have list or dict as a parameter,
    #    specifying what properties are required to have what values

    # TODO: if possible provide a signature that's (temporarily) compatible with
    # old one to ease RF'ing

    # TODO: if assert_intact fails and readonly == True, re-create for other tests

    @better_wraps(t)
    def new_func(*arg, **kw):

        # get selected classes
        # for each class
        #   if read_only, get persistent instance and call assert_intact
        #      if assert_intact failed, rmtree the thing and recreate
        #   else create at a new temp location
        #
        #  - include some parameter or sth for with_testrepos, to let it know
        #    about known_failures to decorate certain calls with
        #    Otherwise, known_failure_XXX needs opt_arg 'testrepo' to pass the
        #    TestRepo class(es) the test does fail on and would need to be used
        #    beneath with_testrepos to get that info.

        #  either just call or yield - not yet sure
        #  t(*(arg + (instance,)), **kw)
        #
        #  if read_only: assert_intact again (Note: recreate not necessary,
        #  since this would be done anyway by the next test requesting this
        # instance. See above.
        pass


@optional_args
def with_testrepos_RF(t, regex='.*', flavors='auto', skip=False, count=None):
    """temporary decorator for RF'ing

    - shares signature with old with_testrepos
    - uses TestRepo.RF_str to determine TestRepos resembling the old ones and
      match them with the same regex
    - tries to do the same thing and deliver the path instead of the object
    - that way we can make (partial) use new consistency and power even without
      rewriting tests
    - may be that entire goal can be achieved without this decorator by simply
      have a function in tests/utils.py that mimics the previous setup, using
      the new repos and rewrites _get_testrepos_uris and whatever is used by it
    """

    pass
