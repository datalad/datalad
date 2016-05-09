# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


# pick ideas from
# http://alextechrants.blogspot.com/2013/08/unit-testing-sqlalchemy-apps.html

from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false

from ..ultimate import UltimateDB

class Test1():
    def setup(self):
        self.udb = UltimateDB()

        pass
    def teardown(self):
        pass

    def test_ultimate1(self):
        udb = self.udb
        with assert_raises(ValueError):
            udb["123"]
        assert_false(udb.get_urls_for_digest(md5="123"))  # there is no check on len with explicit md5 spec

        # sugarings
        assert_false("http://example.com" in udb)
