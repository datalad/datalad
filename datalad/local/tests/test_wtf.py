# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test wtf"""


import os
from os.path import join as opj

import pytest

from datalad import __version__
from datalad.api import (
    create,
    wtf,
)
from datalad.local.wtf import (
    _HIDDEN,
    SECTION_CALLABLES,
    _describe_annex,
    _describe_system,
)
from datalad.support.external_versions import external_versions
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    OBSCURE_FILENAME,
    SkipTest,
    assert_greater,
    assert_in,
    assert_not_in,
    chpwd,
    eq_,
    ok_,
    ok_startswith,
    skip_if_no_module,
    swallow_outputs,
    with_tree,
)
from datalad.utils import ensure_unicode


@with_tree({OBSCURE_FILENAME: {}})
def test_wtf(topdir=None):
    path = opj(topdir, OBSCURE_FILENAME)
    # smoke test for now
    with swallow_outputs() as cmo:
        wtf(dataset=path, on_failure="ignore")
        assert_not_in('## dataset', cmo.out)
        assert_in('## configuration', cmo.out)
        # Those sections get sensored out by default now
        assert_not_in('user.name: ', cmo.out)
    with chpwd(path):
        with swallow_outputs() as cmo:
            wtf()
            assert_not_in('## dataset', cmo.out)
            assert_in('## configuration', cmo.out)
    # now with a dataset
    ds = create(path)
    with swallow_outputs() as cmo:
        wtf(dataset=ds.path)
        assert_in('## configuration', cmo.out)
        assert_in('## dataset', cmo.out)
        assert_in(u'path: {}'.format(ds.path),
                  ensure_unicode(cmo.out))
        assert_in('branches', cmo.out)
        assert_in(DEFAULT_BRANCH+'@', cmo.out)
        assert_in('git-annex@', cmo.out)

    # and if we run with all sensitive
    for sensitive in ('some', True):
        with swallow_outputs() as cmo:
            wtf(dataset=ds.path, sensitive=sensitive)
            # we fake those for tests anyways, but we do show cfg in this mode
            # and explicitly not showing them
            assert_in('user.name: %s' % _HIDDEN, cmo.out)

    with swallow_outputs() as cmo:
        wtf(dataset=ds.path, sensitive='all')
        assert_not_in(_HIDDEN, cmo.out)  # all is shown
        assert_in('user.name: ', cmo.out)
        if external_versions['psutil']:
            if external_versions['psutil'] < '6.0.0':
                # filesystems detail should be reported, unless 6.0.0 where
                # it was removed. See https://github.com/giampaolo/psutil/issues/2109
                assert_in('max_pathlength:', cmo.out)
        else:
            assert_in("Hint: install psutil", cmo.out)

    # Sections selection
    #
    # If we ask for no sections and there is no dataset
    with chpwd(path):
        with swallow_outputs() as cmo:
            wtf(sections=[])
            assert_not_in('## dataset', cmo.out)
            for s in SECTION_CALLABLES:
                assert_not_in('## %s' % s.lower(), cmo.out.lower())

    # ask for a selected set
    secs = ['git-annex', 'configuration']
    with chpwd(path):
        with swallow_outputs() as cmo:
            wtf(sections=secs)
            for s in SECTION_CALLABLES:
                (assert_in if s in secs else assert_not_in)(
                    '## %s' % s.lower(), cmo.out.lower()
                )
            # order should match our desired one, not alphabetical
            # but because of https://github.com/datalad/datalad/issues/3915
            # alphanum is now desired
            assert cmo.out.index('## git-annex') > cmo.out.index('## configuration')

    # not achievable from cmdline is to pass an empty list of sections.
    with chpwd(path):
        with swallow_outputs() as cmo:
            wtf(sections=[])
            eq_(cmo.out.rstrip(), '# WTF')

    # and we could decorate it nicely for embedding e.g. into github issues
    with swallow_outputs() as cmo:
        wtf(sections=['dependencies'], decor='html_details')
        ok_startswith(cmo.out, '<details><summary>DataLad %s WTF' % __version__)
        assert_in('## dependencies', cmo.out)

    # short flavor
    with swallow_outputs() as cmo:
        wtf(flavor='short')
        assert_in("- datalad: version=%s" % __version__, cmo.out)
        assert_in("- dependencies: ", cmo.out)
        eq_(len(cmo.out.splitlines()), 4)  # #WTF, datalad, dependencies, trailing new line

    with swallow_outputs() as cmo:
        wtf(flavor='short', sections='*')
        assert_greater(len(cmo.out.splitlines()), 10)  #  many more

    # check that wtf of an unavailable section yields impossible result (#6712)
    res = wtf(sections=['murkie'], on_failure='ignore')
    eq_(res[0]["status"], "impossible")
    # and we do not get double WTF reporting, while still rendering other sections ok
    with swallow_outputs() as cmo:
        res = wtf(sections=['system', 'murkie', 'environment'], on_failure='ignore')
        assert cmo.out.count('# WTF') == 1  # report produced only ones
        # and we still have other sections requested before or after
        assert cmo.out.count('## system') == 1
        assert cmo.out.count('## environment') == 1
    eq_(res[0]["status"], "impossible")

    # should result only in '# WTF'
    skip_if_no_module('pyperclip')

    # verify that it works correctly in the env/platform
    import pyperclip
    with swallow_outputs() as cmo:
        try:
            pyperclip.copy("xxx")
            pyperclip_works = pyperclip.paste().strip() == "xxx"
            wtf(dataset=ds.path, clipboard=True)
        except (AttributeError, pyperclip.PyperclipException) as exc:
            # AttributeError could come from pyperclip if no DISPLAY
            raise SkipTest(str(exc))
        assert_in("WTF information of length", cmo.out)
        assert_not_in('user.name', cmo.out)
        if not pyperclip_works:
            # Some times does not throw but just fails to work
            raise SkipTest(
                "Pyperclip seems to be not functioning here correctly")
        assert_not_in('user.name', pyperclip.paste())
        assert_in(_HIDDEN, pyperclip.paste())  # by default no sensitive info
        assert_in("cmd:annex:", pyperclip.paste())  # but the content is there


_ANNEX_VERSION_OUTPUT = (
    "git-annex version: 10.20260316\n"
    "build flags: Assistant Webapp MagicMime Testsuite\n"
    "dependency versions: aws-0.25.2 DAV-1.3.4\n"
    "operating system: linux x86_64\n"
)


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_describe_annex_line_endings(eol, monkeypatch):
    """Parse git-annex's output whichever line ending it uses

    The separator is git-annex's business, not the local platform's, so
    splitting on os.linesep dropped everything but `version` wherever the
    two disagreed -- which on Windows is always, leaving `datalad wtf` with
    no build flags, backends or remote types to report.
    """
    stdout = _ANNEX_VERSION_OUTPUT.replace("\n", eol)
    monkeypatch.setattr(
        'datalad.cmd.GitWitlessRunner.run',
        lambda self, *args, **kwargs: dict(stdout=stdout, stderr=''))

    info = _describe_annex()
    eq_(info['version'], '10.20260316')
    eq_(info['build flags'],
        ['Assistant', 'Webapp', 'MagicMime', 'Testsuite'])
    eq_(info['operating system'], 'linux x86_64')


def test_describe_system_cpus():
    """Report both CPU counts, where the platform can tell them apart"""
    cpus = _describe_system()['cpus']
    eq_(cpus['count'], os.cpu_count())
    if hasattr(os, 'sched_getaffinity'):
        assert_greater(cpus['affinity'], 0)
        # a process can be confined to a subset of the machine's CPUs,
        # never granted more than exist
        ok_(cpus['affinity'] <= cpus['count'])
    else:
        assert_not_in('affinity', cpus)


@pytest.mark.skipif(not hasattr(os, 'sched_getaffinity'),
                    reason="no os.sched_getaffinity on this platform")
def test_describe_system_cpus_affinity_failure(monkeypatch):
    """An unreadable affinity mask costs that one field, not the report

    `datalad wtf` is what gets run when something is already wrong, so no
    single probe in it may take the whole report down with it.
    """
    def _boom(pid):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, 'sched_getaffinity', _boom)
    cpus = _describe_system()['cpus']
    eq_(cpus['count'], os.cpu_count())
    assert_not_in('affinity', cpus)
