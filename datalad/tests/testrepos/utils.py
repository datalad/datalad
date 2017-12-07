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
from functools import wraps, partial


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


def _get_all_setups():
    """helper function to get a list of all subclasses of TestRepo_NEW"""

    import inspect
    module = inspect.getmodule(TestRepo_NEW)

    return [module.__dict__[x] for x in module.__dict__
            if inspect.isclass(module.__dict__[x]) and
            issubclass(module.__dict__[x], TestRepo_NEW) and
            module.__dict__[x] is not TestRepo_NEW]

_all_setups = _get_all_setups()


@optional_args
def with_testrepos_new(t, read_only=False, selector=None):
    # selector: regex again?
    # based on class names or name/keyword strings instead?
    # -> May be have TestRepo properties (ItemSelf respectively) like
    #    `is_annex`, `has_submodules`, ... and have list or dict as a parameter,
    #    specifying what properties are required to have what values

    # TODO: For now, let `selector` be a list of classes. We need to figure out
    # a proper approach on that one.

    # default selection: all available test setups; not decorated
    selector = [('all',)] if selector is None else selector[:]

    selected_classes = dict()
    for sel in selector:
        if sel[0] == 'all':
            # special case for convenience: use all available test setups and
            # optionally apply an additional decorator to the test, which is
            # technically applied on a per test setup basis
            for cls_ in _all_setups:
                if cls_.__name__ not in selected_classes:
                    # initialize entry for that class, if there wasn't one
                    # before:
                    selected_classes[cls_.__name__] = dict()
                    selected_classes[cls_.__name__]['class'] = cls_
                    selected_classes[cls_.__name__]['decorator'] = lambda x: x

                if len(sel) > 1:
                    # apply decorator:
                    selected_classes[cls_.__name__]['decorator'] = sel[1]
        else:
            if sel[0].__name__ not in selected_classes:
                # initialize entry for that class, if there wasn't one
                # before:
                selected_classes[sel[0].__name__] = dict()
                selected_classes[sel[0].__name__]['class'] = sel[0]
                selected_classes[sel[0].__name__]['decorator'] = lambda x: x
            if len(sel) > 1:
                # apply decorator:
                selected_classes[sel[0].__name__]['decorator'] = sel[1]

    # TODO: Why in hell `better_wraps` prevents nose from discovering the
    # decorated test (when yielding them), while:
    #     1. `functools.wraps` doesn't AND
    #     2. `optional_args` uses `better_wraps`, too, and
    #        still works?
    # @better_wraps(t)
    @wraps(t)
    def newfunc(*arg, **kw):

        from nose import SkipTest

        @optional_args
        def assure_raise(func):
            """decorator to help mimic the raise came from within the test"""
            @wraps(func)
            def newfunc(cls_, exc, **kw):
                raise exc
            return newfunc

        for class_name in selected_classes:
            lgr.debug("delivering testrepo '%s'", class_name)
            decorated_test = selected_classes[class_name]['decorator'](t)

            if read_only:
                # Note, that `get_persistent_setup` calls assert_intact
                # already and re-creates if needed.
                try:
                    testrepo = get_persistent_setup(
                        selected_classes[class_name]['class'])()
                except SkipTest as e:
                    # We got a SkipTest on creation.
                    # At this point nose doesn't recognize we are actually
                    # building several tests. So we need to yield a function,
                    # that raises SkipTest and still provides the tests name and
                    # arguments in order to have a telling output by nose.
                    yield partial(assure_raise(decorated_test),
                                  exc=e, *arg, **kw), \
                          selected_classes[class_name]['class']
                    continue

                yield partial(decorated_test, *arg, **kw), testrepo
                testrepo.assert_intact()

            else:
                # create a new one in a temp location:
                with make_tempfile(wrapped=t, mkdir=True) as path:
                    try:
                        testrepo = \
                            selected_classes[class_name]['class'](path=path)
                    except SkipTest as e:
                        # We got a SkipTest on creation.
                        # At this point nose doesn't recognize we are actually
                        # building several tests. So we need to yield a
                        # function, that raises SkipTest and still provides the
                        # tests name and arguments in order to have a telling
                        # output by nose.
                        yield partial(assure_raise(decorated_test),
                                      exc=e, *arg, **kw), \
                              selected_classes[class_name]['class']
                        continue

                    yield partial(decorated_test, *arg, **kw), testrepo

    return newfunc
# don't let nose consider this function to be a test (based on its name):
with_testrepos_new.__test__ = False


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
