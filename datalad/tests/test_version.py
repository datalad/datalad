# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import re

from packaging.version import Version

from datalad.support import path as op
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_greater,
    assert_in,
    assert_not_in,
    ok_startswith,
)
from datalad.utils import ensure_unicode

from .. import __version__


def test__version__():
    # in released stage, version in the last CHANGELOG entry
    # should correspond to the one in datalad
    CHANGELOG_filename = op.join(
        op.dirname(__file__), op.pardir, op.pardir, 'CHANGELOG.md')
    if not op.exists(CHANGELOG_filename):
        raise SkipTest("no %s found" % CHANGELOG_filename)
    regex = re.compile(r'^# '
                       r'(?P<version>[0-9]+\.[0-9.abcrc~]+)\s+'
                       r'\((?P<date>.*)\)'
                       )
    with open(CHANGELOG_filename, 'rb') as f:
        for line in f:
            line = line.rstrip()
            if not line.startswith(b'# '):
                # The first section header we hit, must be our changelog entry
                continue
            reg = regex.match(ensure_unicode(line))
            if not reg:  # first one at that level is the one
                raise AssertionError(
                    "Following line must have matched our regex: %r" % line)
            regd = reg.groupdict()
            changelog_version = regd['version']
            lv_changelog_version = Version(changelog_version)
            # we might have a suffix - sanitize
            san__version__ = __version__.rstrip('.dirty')
            lv__version__ = Version(san__version__)
            if '???' in regd['date'] and 'will be better than ever' in regd['codename']:
                # we only have our template
                # we can only assert that its version should be higher than
                # the one we have now
                assert_greater(lv_changelog_version, lv__version__)
            else:
                # should be a "release" record
                assert_not_in('???', regd['date'])
                ok_startswith(__version__, changelog_version)
                if lv__version__ != lv_changelog_version:
                    # It was not tagged yet and Changelog has no new records
                    # (they are composed by auto upon release)
                    assert_greater(lv__version__, lv_changelog_version)
                    assert_in('+', san__version__)  # we have build suffix
                else:
                    # all is good, tagged etc
                    assert_equal(lv_changelog_version, lv__version__)
                    assert_equal(changelog_version, san__version__)
            return

    raise AssertionError(
        "No log line matching our regex found in %s" % CHANGELOG_filename
    )
