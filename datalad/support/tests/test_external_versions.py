# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the duecredit package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os import linesep

from ..version import __version__
from ..versions import ExternalVersions, StrictVersion

from nose.tools import assert_true, assert_false
from nose.tools import assert_equal, assert_greater_equal, assert_greater
from nose.tools import assert_raises
from nose import SkipTest
from six import PY3

if PY3:
    # just to ease testing
    def cmp(a, b):
        return (a > b) - (a < b)

def test_external_versions_basic():
    ev = ExternalVersions()
    assert_equal(ev._versions, {})
    assert_equal(ev['duecredit'], __version__)
    # and it could be compared
    assert_greater_equal(ev['duecredit'], __version__)
    assert_greater(ev['duecredit'], '0.1')
    assert_equal(list(ev.keys()), ['duecredit'])
    assert_true('duecredit' in ev)
    assert_false('unknown' in ev)

    # StrictVersion might remove training .0
    version_str = str(ev['duecredit']) \
        if isinstance(ev['duecredit'], StrictVersion) \
        else __version__
    assert_equal(ev.dumps(), "Versions: duecredit=%s" % version_str)

    # For non-existing one we get None
    assert_equal(ev['duecreditnonexisting'], None)
    # and nothing gets added to _versions for nonexisting
    assert_equal(set(ev._versions.keys()), {'duecredit'})

    # but if it is a module without version, we get it set to UNKNOWN
    assert_equal(ev['os'], ev.UNKNOWN)
    # And get a record on that inside
    assert_equal(ev._versions.get('os'), ev.UNKNOWN)
    # And that thing is "True", i.e. present
    assert(ev['os'])
    # but not comparable with anything besides itself (was above)
    assert_raises(TypeError, cmp, ev['os'], '0')
    assert_raises(TypeError, assert_greater, ev['os'], '0')

    # And we can get versions based on modules themselves
    from duecredit.tests import mod
    assert_equal(ev[mod], mod.__version__)

    # Check that we can get a copy of the versions
    versions_dict = ev.versions
    versions_dict['duecredit'] = "0.0.1"
    assert_equal(versions_dict['duecredit'], "0.0.1")
    assert_equal(ev['duecredit'], __version__)


def test_external_versions_unknown():
    assert_equal(str(ExternalVersions.UNKNOWN), 'UNKNOWN')


def _test_external(ev, modname):
    try:
        exec ("import %s" % modname, globals(), locals())
    except ImportError:
        raise SkipTest("External %s not present" % modname)
    except Exception as e:
        raise SkipTest("External %s fails to import: %s" % (modname, e))
    assert (ev[modname] is not ev.UNKNOWN)
    assert_greater(ev[modname], '0.0.1')
    assert_greater('1000000.0', ev[modname])  # unlikely in our lifetimes


def test_external_versions_popular_packages():
    ev = ExternalVersions()

    for modname in ('scipy', 'numpy', 'mvpa2', 'sklearn', 'statsmodels', 'pandas',
                    'matplotlib', 'psychopy'):
        yield _test_external, ev, modname

    # more of a smoke test
    assert_false(linesep in ev.dumps())
    assert_true(ev.dumps(indent=True).endswith(linesep))