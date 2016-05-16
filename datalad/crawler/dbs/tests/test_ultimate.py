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
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_true
from datalad.tests.utils import with_tempfile

from ..ultimate import UltimateDB, File

from datalad.support.tests.test_digests import SAMPLE_DIGESTS

class Test1():
    def setup(self):
        self.udb = UltimateDB(auto_connect=True)

    def teardown(self):
        pass

    def test_ultimate1(self):
        udb = self.udb
        with assert_raises(ValueError):
            udb["123"]
        assert_false(udb.get_urls_for_digest(md5="123"))  # there is no check on len with explicit md5 spec

        # sugarings
        assert_false("http://example.com" in udb)

    @with_tempfile(content="123")
    def test_process_file(self, f):
        digests = SAMPLE_DIGESTS["123"]
        assert_equal(self.udb.process_file(f), digests)  # outputs all digests atm
        # This should create all entries in the DB so let's request information
        assert_true(self.udb.has_file_with_digests(**digests))
        assert_false(self.udb.has_file_with_digests(**SAMPLE_DIGESTS["__long__"]))