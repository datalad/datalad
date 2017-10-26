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
import logging

from .. import _TEMP_PATHS_GENERATED
from ..utils import get_tempfile_kwargs
from ...utils import make_tempfile
from ...utils import better_wraps
from ...utils import optional_args
from .repos import *


lgr = logging.getLogger('datalad.tests.testrepos.utils')
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

    # TODO: For now, let `selector` be a list of classes. We need to figure out
    # a proper approach on that one.
    if selector == 'all':
        selected_classes = [BasicGit, BasicMixed, MixedSubmodulesOldOneLevel,
                            MixedSubmodulesOldNested]
    else:
        selected_classes = selector

    @better_wraps(t)
    def new_func(*arg, **kw):

        for cls_ in selected_classes:
            lgr.debug("delivering testrepo '%s'", cls_.__name__)
            if read_only:
                # Note, that `get_persistent_testrepo` calls assert_intact
                # already and re-creates if needed.
                testrepo = get_persistent_testrepo(cls_)()
                t(*(arg + (testrepo,)), **kw)
                testrepo.assert_intact()
            else:
                # create a new one in a temp location:
                with make_tempfile(wrapped=t, mkdir=True) as path:
                    testrepo = cls_(path=path)
                    t(*(arg + (testrepo,)), **kw)

    return new_func


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
