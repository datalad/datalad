# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test wtf"""


from os.path import join as opj

from datalad.dochelpers import exc_str
from datalad.api import (
    create,
    wtf,
)
from datalad.local.wtf import (
    _HIDDEN,
    SECTION_CALLABLES,
)
from datalad.version import __version__

from datalad.utils import ensure_unicode
from datalad.tests.utils import (
    assert_greater,
    assert_in,
    assert_not_in,
    chpwd,
    eq_,
    OBSCURE_FILENAME,
    ok_startswith,
    skip_if_no_module,
    SkipTest,
    swallow_outputs,
    with_tree,
    DEFAULT_BRANCH
)


@with_tree({OBSCURE_FILENAME: {}})
def test_wtf(topdir):
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
            raise SkipTest(exc_str(exc))
        assert_in("WTF information of length", cmo.out)
        assert_not_in('user.name', cmo.out)
        if not pyperclip_works:
            # Some times does not throw but just fails to work
            raise SkipTest(
                "Pyperclip seems to be not functioning here correctly")
        assert_not_in('user.name', pyperclip.paste())
        assert_in(_HIDDEN, pyperclip.paste())  # by default no sensitive info
        assert_in("cmd:annex:", pyperclip.paste())  # but the content is there
