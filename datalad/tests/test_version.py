# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import re
from distutils.version import LooseVersion

from ..version import (
    __version__,
    __hardcoded_version__,
)
from ..support import path as op
from ..utils import assure_unicode
from .utils import (
    assert_equal,
    assert_greater,
    assert_not_in,
    assert_in,
    SkipTest,
)


def test__version__():
    # in released stage, version in the last CHANGELOG entry
    # should correspond to the one in datalad
    CHANGELOG_filename = op.join(
        op.dirname(__file__), op.pardir, op.pardir, 'CHANGELOG.md')
    if not op.exists(CHANGELOG_filename):
        raise SkipTest("no %s found" % CHANGELOG_filename)
    regex = re.compile(r'^## '
                       r'(?P<version>[0-9]+\.[0-9.abcrc~]+)\s+'
                       r'\((?P<date>.*)\)'
                       r'\s+--\s+'
                       r'(?P<codename>.+)'
                       )
    with open(CHANGELOG_filename, 'rb') as f:
        for line in f:
            line = line.rstrip()
            if not line.startswith(b'## '):
                # The first section header we hit, must be our changelog entry
                continue
            reg = regex.match(assure_unicode(line))
            if not reg:  # first one at that level is the one
                raise AssertionError(
                    "Following line must have matched our regex: %r" % line)
            regd = reg.groupdict()
            changelog_version = regd['version']
            lv_changelog_version = LooseVersion(changelog_version)
            # we might have a suffix - sanitize
            san__version__ = __version__.rstrip('.devdirty')
            lv__version__ = LooseVersion(san__version__)
            if '???' in regd['date'] and 'will be better than ever' in regd['codename']:
                # we only have our template
                # we can only assert that its version should be higher than
                # the one we have now
                assert_greater(lv_changelog_version, lv__version__)
            else:
                # should be a "release" record
                assert_not_in('???', regd['date'])
                assert_not_in('will be better than ever', regd['codename'])
                assert_equal(__hardcoded_version__, changelog_version)
                if __hardcoded_version__ != san__version__:
                    # It was not tagged yet!
                    assert_greater(lv_changelog_version, lv__version__)
                    assert_in('.dev', san__version__)
                else:
                    # all is good, tagged etc
                    assert_equal(lv_changelog_version, lv__version__)
                    assert_equal(changelog_version, san__version__)
                    assert_equal(__hardcoded_version__, san__version__)
            return

    raise AssertionError(
        "No log line matching our regex found in %s" % CHANGELOG_filename
    )