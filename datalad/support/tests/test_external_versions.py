# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
from os import linesep

from datalad import __version__
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    CommandError,
    MissingExternalDependency,
    OutdatedExternalDependency,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_false,
    assert_greater,
    assert_greater_equal,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_true,
    create_tree,
    patch,
    set_annex_version,
    swallow_logs,
    with_tempfile,
)

from ..external_versions import (
    ExternalVersions,
    LooseVersion,
)


# just to ease testing
def cmp(a, b):
    return (a > b) - (a < b)


def test_external_versions_basic():
    ev = ExternalVersions()
    our_module = 'datalad'
    assert_equal(ev.versions, {})
    assert_equal(ev[our_module], __version__)
    # and it could be compared
    assert_greater_equal(ev[our_module], __version__)
    # We got some odd failure in this test not long are after switching to versionner
    # https://github.com/datalad/datalad/issues/5785.  Verify that we do get expected
    # data types
    our_version = ev[our_module].version
    assert isinstance(our_version, (str, list)), f"Got {our_version!r} of type {type(our_version)}"
    assert_greater(ev[our_module], '0.1')
    assert_equal(list(ev.keys()), [our_module])
    assert_true(our_module in ev)
    assert_false('unknown' in ev)

    # all are LooseVersions now
    assert_true(isinstance(ev[our_module], LooseVersion))
    version_str = __version__
    assert_equal(ev.dumps(), "Versions: %s=%s" % (our_module, version_str))

    # For non-existing one we get None
    assert_equal(ev['custom__nonexisting'], None)
    # and nothing gets added to _versions for nonexisting
    assert_equal(set(ev.versions.keys()), {our_module})

    # but if it is a module without version, we get it set to UNKNOWN
    assert_equal(ev['os'], ev.UNKNOWN)
    # And get a record on that inside
    assert_equal(ev.versions.get('os'), ev.UNKNOWN)
    # And that thing is "True", i.e. present
    assert(ev['os'])
    # but not comparable with anything besides itself (was above)
    assert_raises(TypeError, cmp, ev['os'], '0')
    assert_raises(TypeError, assert_greater, ev['os'], '0')

    return
    ## Code below is from original duecredit, and we don't care about
    ## testing this one
    ## And we can get versions based on modules themselves
    #from datalad.tests import mod
    #assert_equal(ev[mod], mod.__version__)

    ## Check that we can get a copy of the versions
    #versions_dict = ev.versions
    #versions_dict[our_module] = "0.0.1"
    #assert_equal(versions_dict[our_module], "0.0.1")
    #assert_equal(ev[our_module], __version__)


def test_external_version_contains():
    ev = ExternalVersions()
    assert_true("datalad" in ev)
    assert_false("does not exist" in ev)


def test_external_versions_unknown():
    assert_equal(str(ExternalVersions.UNKNOWN), 'UNKNOWN')


def _test_external(ev, modname):
    try:
        exec("import %s" % modname, globals(), locals())
    except ImportError:
        raise SkipTest("External %s not present" % modname)
    except Exception as e:
        raise SkipTest("External %s fails to import" % modname) from e
    assert (ev[modname] is not ev.UNKNOWN)
    assert_greater(ev[modname], '0.0.1')
    assert_greater('1000000.0', ev[modname])  # unlikely in our lifetimes


def test_external_versions_popular_packages():
    ev = ExternalVersions()

    for modname in ('scipy', 'numpy', 'mvpa2', 'sklearn', 'statsmodels', 'pandas',
                    'matplotlib', 'psychopy', 'github'):
        _test_external(ev, modname)

    # more of a smoke test
    assert_false(linesep in ev.dumps())
    assert_true(ev.dumps(indent=True).endswith(linesep))


@with_tempfile(mkdir=True)
def test_external_versions_rogue_module(topd=None):
    ev = ExternalVersions()
    # if module throws some other non-ImportError exception upon import
    # we must not crash, but issue a warning
    modname = 'verycustomrogue__'
    create_tree(topd, {modname + '.py': 'raise Exception("pickaboo")'})
    with patch('sys.path', [topd]), \
        swallow_logs(new_level=logging.WARNING) as cml:
        assert ev[modname] is None
        assert_true(ev.dumps(indent=True).endswith(linesep))
        assert_in('pickaboo', cml.out)


def test_custom_versions():
    ev = ExternalVersions()
    assert(ev['cmd:annex'] > '6.20160101')  # annex must be present and recentish
    assert_equal(set(ev.versions.keys()), {'cmd:annex'})
    # some older git version don't support files to be passed to
    # `commit` call under some conditions and this will lead to diverse
    # errors
    assert(ev['cmd:git'] > '2.0')  # git must be present and recentish
    assert(isinstance(ev['cmd:git'], LooseVersion))
    assert_equal(set(ev.versions.keys()), {'cmd:annex', 'cmd:git'})

    # and there is also a version of system-wide installed git, which might
    # differ from cmd:git but should be at least good old 1.7
    assert(ev['cmd:system-git'] > '1.7')

    ev.CUSTOM = {'bogus': lambda: 1 / 0}
    assert_equal(ev['bogus'], None)
    assert_equal(set(ev.versions), {'cmd:annex', 'cmd:git', 'cmd:system-git'})


def test_ancient_annex():

    class _runner(object):
        def run(self, cmd, *args, **kwargs):
            if '--raw' in cmd:
                raise CommandError
            return dict(stdout="git-annex version: 0.1", stderr="")

    ev = ExternalVersions()
    with patch('datalad.support.external_versions._runner', _runner()):
        assert_equal(ev['cmd:annex'], '0.1')


def _test_annex_version_comparison(v, cmp_):
    class _runner(object):
        def run(self, cmd, *args, **kwargs):
            return dict(stdout=v, stderr="")

    ev = ExternalVersions()
    with set_annex_version(None), \
         patch('datalad.support.external_versions._runner', _runner()), \
         patch('datalad.support.annexrepo.external_versions',
               ExternalVersions()):
        ev['cmd:annex'] < AnnexRepo.GIT_ANNEX_MIN_VERSION
        if cmp_ in (1, 0):
            AnnexRepo._check_git_annex_version()
            if cmp_ == 0:
                assert_equal(AnnexRepo.git_annex_version, v)
        elif cmp == -1:
            with assert_raises(OutdatedExternalDependency):
                ev.check('cmd:annex', min_version=AnnexRepo.GIT_ANNEX_MIN_VERSION)
            with assert_raises(OutdatedExternalDependency):
                AnnexRepo._check_git_annex_version()


def test_annex_version_comparison():
    # see https://github.com/datalad/datalad/issues/1128
    for cmp_, base in [(-1, '6.2011'), (1, "2100.0")]:
        # there could be differing versions of a version
        #   release, snapshot, neurodebian build of a snapshot
        for v in base, base + '-g0a34f08', base + '+gitg9f179ae-1~ndall+1':
            # they all must be comparable to our specification of min version
            _test_annex_version_comparison(v, cmp_)
    _test_annex_version_comparison(str(AnnexRepo.GIT_ANNEX_MIN_VERSION), 0)


def _test_list_tuple(thing):
    version = ExternalVersions._deduce_version(thing)
    assert_greater(version, '0.0.1')
    assert_greater('0.2', version)
    assert_equal('0.1', version)
    assert_equal(version, '0.1')


def test_list_tuple():

    class thing_with_tuple_version:
        __version__ = (0, 1)

    class thing_with_list_version:
        __version__ = [0, 1]

    for v in thing_with_list_version, thing_with_tuple_version, '0.1', (0, 1), [0, 1]:
        _test_list_tuple(v)


def test_system_ssh_version():
    ev = ExternalVersions()
    assert ev['cmd:system-ssh']  # usually we have some available at boxes we test

    for s, v in [
        ('OpenSSH_7.4p1 Debian-6, OpenSSL 1.0.2k  26 Jan 2017', '7.4p1'),
        ('OpenSSH_8.1p1, LibreSSL 2.7.3', '8.1p1'),
        ('OpenSSH_for_Windows_8.1p1, LibreSSL 3.0.2', '8.1p1'),
    ]:
        ev = ExternalVersions()
        # TODO: figure out leaner way
        class _runner(object):
            def run(self, cmd, *args, **kwargs):
                return dict(stdout="", stderr=s)
        with patch('datalad.support.external_versions._runner', _runner()):
            assert_equal(ev['cmd:system-ssh'], v)


def test_humanize():
    # doesn't provide __version__
    assert ExternalVersions()['humanize']


def test_check():
    ev = ExternalVersions()
    # should be all good
    ev.check('datalad')
    ev.check('datalad', min_version=__version__)

    with assert_raises(MissingExternalDependency):
        ev.check('dataladkukaracha')
    with assert_raises(MissingExternalDependency) as cme:
        ev.check('dataladkukaracha', min_version="buga", msg="duga")

    assert_in("duga", str(cme.value))

    with assert_raises(OutdatedExternalDependency):
        ev.check('datalad', min_version="10000000")  # we will never get there!


def test_add():
    ev = ExternalVersions()
    ev.add('custom1', lambda: "0.1.0")
    assert_in("custom1=0.1.0", ev.dumps(query=True))
    assert_not_in("numpy", ev.INTERESTING)  # we do not have it by default yet
    assert_not_in("numpy=", ev.dumps(query=True))
    ev.add('numpy')
    try:
        import numpy
    except ImportError:
        # no numpy, we do not have some bogus entry
        assert_not_in("numpy=", ev.dumps(query=True))
    else:
        assert_in("numpy=%s" % numpy.__version__, ev.dumps(query=True))
    assert_in("custom1=0.1.0", ev.dumps(query=True))  # we still have that one

    # override with a new function will work
    ev.add('custom1', lambda: "0.2.0")
    assert_in("custom1=0.2.0", ev.dumps(query=True))
