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

from ..ultimate import UltimateDB

from datalad.support.tests.test_digests import SAMPLE_DIGESTS

from mock import patch

class Test1():
    def setup(self):
        self.udb = UltimateDB(auto_connect=True)

    def teardown(self):
        pass

    def test_ultimate1(self):
        udb = self.udb
        with assert_raises(ValueError):
            udb["123"]
        assert_false(udb.get_file_with_digest(md5="123"))
        # but we would raise if asking for urls for non existing file
        assert_raises(ValueError, udb.get_urls_with_digest, md5="123")
        # sugarings
        assert_false("http://example.com" in udb)

    @with_tempfile(content="123")
    def test_process_file(self, f):
        digests = SAMPLE_DIGESTS["123"]
        file_ = self.udb.process_file(f)
        assert_equal(file_.get_digests(), digests)  # outputs all digests atm
        # This should create all entries in the DB so let's request information
        assert_true(self.udb.has_file_with_digests(**digests))
        assert_false(self.udb.has_file_with_digests(**SAMPLE_DIGESTS["__long__"]))

    @with_tempfile(content="123")
    def test_context_manager_single_commit(self, f):
        bogus_key = "123"
        with patch.object(self.udb._session, 'commit') as patched_commit:
            with self.udb as db:
                assert(db is self.udb)  # we are just returning itself for convenience
                # multiple operations
                file_ = db.process_file(f)
                assert_raises(AssertionError, db.get_key, bogus_key)
                key_ = db.get_key(bogus_key, file_)
                assert_true(key_ is not None)
                patched_commit.assert_not_called()
            patched_commit.assert_called_once_with()

    @with_tempfile(content="123")
    def test_context_manager_single_commit_nested(self, f):
        # and now just a nested one
        with patch.object(self.udb._session, 'commit') as patched_commit:
            with self.udb:
                with self.udb:
                    self.udb.process_file(f)
                    patched_commit.assert_not_called()
                patched_commit.assert_not_called()
            patched_commit.assert_called_once_with()

    @with_tempfile(content="123")
    def test_urls_basic1(self, f):
        urls = []
        file_ = self.udb.process_file(f)
        digests = file_.get_digests()
        for algo, checksum in digests.items():
            assert_equal(self.udb.get_urls_with_digest(checksum), urls)
            # atm takes only a single digest value
            assert_equal(self.udb.get_urls_with_digest(**{algo: checksum}), urls)

        # now add a url
        from ..ultimate_orm import URL
        url1 = "http://example.datalad.org/123"
        url2 = "http://example.datalad.org/123+1"
        url = self.udb.add_url(file_, url1)
        # TODO: assert_recent(url.last_checked)
        assert_equal(url.last_checked, url.first_checked)
        # by default is not marked as validated
        assert_equal(url.last_validated, None)
        assert_equal(url.valid, None)

        assert_equal(self.udb.get_urls(file_), [])
        assert_equal(self.udb.get_urls(file_, valid_only=False), [url1])
        assert_equal(self.udb.get_urls_with_digest(checksum, valid_only=False), [url1])

        # if we add the same but now validated, we still should have just 1 url
        url = self.udb.add_url(file_, url1, valid=True)
        assert_true(url.last_validated is not None)
        assert_equal(url.last_validated, url.first_validated)
        assert_true(url.valid)
        assert_false(url.last_checked == url.first_checked)
        assert_equal(self.udb.get_urls(file_), [url1])
        assert_equal(self.udb.get_urls(file_, valid_only=False), [url1])

        # And lets add url2 which would not be validated
        url = self.udb.add_url(file_, url2)
        assert_equal(self.udb.get_urls(file_), [url1])
        assert_equal(self.udb.get_urls(file_, valid_only=False), [url1, url2])
        assert_equal(self.udb.get_urls_with_digest(checksum, valid_only=False), [url1, url2])

        # and for paranoid assure that DB has them now
        assert_equal(len(list(self.udb._query(URL))), 2)
        assert_equal(len(list(self.udb._query(URL).filter_by(file_id=file_.id))), 2)
