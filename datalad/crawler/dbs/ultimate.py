# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to provide Ultimate DB to store URLs, checksums, etc to cross-pollinate across handles/sources"""

from datetime import datetime

import os
import time
from abc import ABCMeta, abstractmethod, abstractproperty

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.engine.reflection import Inspector

from ...support.digests import Digester
from .ultimate_orm import File as oFile, URL as oURL, Key as oKey, DBTable

# for now lazy/ignorant yoh would just use/pass ORM's objects around
# oFile -> file,
# oURL -> url, ...

import logging
from logging import getLogger
lgr = getLogger('datalad.crawler.dbs.ultimate')

# Terminology used through out this module
#  digest is an  algo: checksum  pair
#  checked -- checked to exist
#  valid -- validated to contain promised content.  So 'valid' but 'last_validated' in DB

# Assuming that we are dealing always with hex representations of the digests, which could
# be more concisely (twice shorter) represented in actual binary
LEN_TO_ALGO = {
    32: 'md5',
    40: 'sha1',
    64: 'sha256',
    128: 'sha512'
}
KNOWN_ALGO = set(LEN_TO_ALGO.values())
assert(set(Digester.DEFAULT_DIGESTS) == KNOWN_ALGO)
DEFAULT_ALGO = "sha256"

from datalad import cfg

class HashCollisionError(ValueError):
    """Exception to "celebrate" -- we ran into a hash collision.  World should skip a bit"""
    pass


def _get_digest_value(checksum=None, **digest):
    """Just a helper so we could simply provide a value or specify which algorithm

    Returns
    -------
    dict:
      1 element dictionary {digest: value}
    """
    if digest:
        if len(digest) > 1 or (digest.keys()[0] not in KNOWN_ALGO) or checksum:
            raise ValueError(
                "You must either specify checksum= or explicitly "
                "one of known digests %s. Got %r" % (KNOWN_ALGO, digest))
    else:
        try:
            digest = {LEN_TO_ALGO[len(checksum)]: checksum}
        except:
            raise ValueError("Checksum %s of len %d has no known digest algorithm"
                             % (checksum, len(checksum)))
            # may be at some point we would like to find one based on the leading
            # few characters of the checksum but not atm
    return digest


class UltimateDB(object):
    """Database collating urls for the content across all handles

    Schema: below via sqlalchemy

        or should there be some kind of separate checking/validation transaction log table(s),
        so we could have full "history"

        entry, url, date, status (OK, NOK, FAIL), fail_reason

        ? then we could deduce first/last if necessary

      Q: should we have independent entries (urls) for the same URL, e.g. we can access
         public S3 via s3:// http:// and https://.  But some of them might become unavailable
         (e.g. public goes private, or other obstacles).  So easiest to keep separate but then
         should we have any notion that they actually point to the same physical object???

    May be separate db or table(s) for internal tracking of annexes/repositories containing
    keys

    - entry <<->> annex uuid,  and annex uuid <->> path
      - theoretically it should be uuid -> path  (but we can't guarantee it ;) )
      - should we have uuid <->> URL (i.e. knowing remote locations for repos just in case?)

      Such DB would allow to locate physical load on our drives happen we want it without downloading
      from online.  Would also allow for fancy "know not only from where to download 1 file, but
      what to clone to get it".  Then for each URL we would need the same attributes (could be a table
      with identical schema to the above)


    """

    # __metaclass__ = ABCMeta

    # XXX should become a singleton?  so we could access the same DB from e.g.
    # nodes.Annex and add_archive_content

    def __init__(self, digester=None, auto_connect=False):
        self._digester = digester or Digester(list(KNOWN_ALGO))
        self._session = None
        self._contexts = []  # so we could commit upon exiting the last cm
        if auto_connect:
            self.connect()

    # XXX or should this be reserved for checksums?
    #  probably so since __getitem__ operates on checksums -- TODO
    def __contains__(self, url):
        return self.has_file_with_url(url)

    #@abstractmethod
    def __getitem__(self, checksum=None):
        return self.get_urls_with_digest(checksum)

    @staticmethod
    def _initiate_db(engine):
        lgr.info("Initiating Ultimate DB tables")
        return DBTable.metadata.create_all(engine)

    def _handle_collision(self, digest):
        raise HashCollisionError("??? multiple entries for %s" % str(digest))

    def connect(self, url='sqlite:///:memory:', username=None, password=None):
        # TODO: might want to "grasp" http://stackoverflow.com/a/8705750
        # and avoid creating this factory over and over again?
        # TODO: also this is nohow thread/multiprocess safe ATM
        engine = create_engine(url)
        # see http://docs.sqlalchemy.org/en/latest/core/pooling.html
        # may be we need some customization here
        # TODO:  see http://docs.sqlalchemy.org/en/latest/core/pooling.html#using-connection-pools-with-multiprocessing
        # for when we would start multithreading etc
        # set logging.... for some reason not in effect at all
        if lgr.getEffectiveLevel() <= 5:
            lgr.debug("Raising logging level for sqlalchemy and making it use our logger")
            getLogger('sqlalchemy').setLevel(logging.INFO)
            getLogger('sqlalchemy').handlers = lgr.handlers

        # check if we have tables initiated already in the DB
        inspector = Inspector.from_engine(engine)
        if not inspector.get_table_names():
            self._initiate_db(engine)

        self._session = Session(bind=engine)

    def disconnect(self):
        if not self._session:
            return
        self._session.commit()  # to flush any changes which might have been staged
        self._contexts = []
        # TODO: is there more to do to close it "properly"?
        self._session = None
        # I guess that will also lead to complete destroying of engine if session is gone

    @staticmethod
    def _parse_db_url(url):
        import re
        # dialect[+driver]://user:password@host:port/dbname[?key=value..]
        # interesting -- can't : or / be used in the passw?
        r = re.compile(r"""(?P<dialect>[^:]*)://                 # dialect[+driver]://
                           (?P<user>[^:/@]+)?(?::(?P<password>[^:/@]*))? # user:password
                           (?:@(?P<host>[^:/@]+)(?::(?P<port>\d+))?)?/                  # @host/
                           (?P<dbname>\S+)(?:\?(?P<options>.*))? # dbname[?key=value..]
                        """,
                       re.X)
        reg = re.match(r, url)
        if not reg:
            raise ValueError(
                "URL for the ultimatedb should conform to the specification "
                "expected by sqlalchemy. "
                "See http://docs.sqlalchemy.org/en/rel_1_1/core/engines.html")
        return reg.groupdict()

    @classmethod
    def from_config(cls):
        """Factory to provide instance initiated based on config settings"""
        db = cls()
        url = cfg.getboolean('crawl', 'ultimatedb.url')
        # may be we should use "centralized" credential specification?
        #credential = cfg.get('ultimatedb', 'credential')

        # Parse url, since if contains credentials, no need to check config
        url_rec = cls._parse_db_url(url)
        if url_rec['user']:
            credkw = {
                'user': url_rec['user'],
                'password': url_rec['password']
            }
        else:
            lgr.debug("Obtaining credentials for ultimatedb from config/credentials")
            try:
                cred_name = cfg.get('crawl', 'ultimatedb.credname')
                cred_type = cfg.get('crawl', 'ultimatedb.credtype', default="user_password")
            except IOError:  # TODO differerent
                lgr.debug("No mentioning of credname for ultimatedb in config")
                cred_name = None
            if cred_name:
                # request credential information
                from datalad.downloaders.providers import Credential
                cred = Credential(cred_name, cred_type)
                assert(set(cred.keys()) == {'user', 'password'})
                credkw = cred()
            else:
                credkw = {}
        db.connect(url=url, **credkw)

    #
    # Helpers
    #

    def _commit(self):
        """Would commit if outside of the cm"""
        if not self._contexts:
            self._session.commit()

    def _add(self, obj):
        """Helper to add a new object to the session"""
        self._session.add(obj)
        self._commit()
        return obj

    def _query(self, *args, **kwargs):
        return self._session.query(*args, **kwargs)

    # Context manager so we could group multiple operations
    def __enter__(self, force_commit=False):
        """

        force_commit:
         Either to force commit, if not, only existing outter most cm would force commit
        """
        # TODO: actually we can't pass options such as force_commit if implemented as part of this class
        # could have been just a counter I guess
        self._contexts.append(force_commit)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        commit = self._contexts.pop(-1)
        if commit or not self._contexts:
            lgr.debug("Committing UDB upon leaving cm")
            self._session.commit()


    def has_file_with_url(self, url):  # TODO: valid_only ?
        """Return True if DB knows about this URL (as associated with a file)"""
        return self._query(oURL.id).filter_by(url=url).first() is not None

    def has_file_with_digests(self, **digests):
        # XXX may be relax allowing for arbitrary set of digests or just a checksum being provided
        assert set(digests) == KNOWN_ALGO, "Provide all digests for a file of interest"
        # search by default one
        try:
            digest = {DEFAULT_ALGO: digests[DEFAULT_ALGO]}
            file_ = self._query(oFile).filter_by(**digest).one()
        except NoResultFound:
            return False
        except MultipleResultsFound:
            return self._handle_collision(digest)

        # otherwise check if other digests correspond
        for algo, checksum in digests.items():
            if getattr(file_, algo) != checksum:
                raise HashCollisionError(
                    "%s %s != %s.  Full entries: %s, %s"
                    % (algo, getattr(file_, algo), checksum, digests, file_)
                )
        return True

    def get_file_with_digest(self, checksum=None, **digest):
        """Return File object matching the checksum
        """
        digest = _get_digest_value(checksum, **digest)
        try:
            file_ = self._query(oFile).filter_by(**digest).one()
        except NoResultFound:
            return None
        except MultipleResultsFound:
            return self._handle_collision(digest)
        return file_

    def get_urls_with_digest(self, checksum=None, valid_only=True, **digest):
        """Given a checksum, return URLs where it is available from

        Parameters
        ----------
        checksum: str
          Arbitrary checksum -- we will figure out which one
        **digest:
          Should include only one of the checksums, e.g.
          md5='...'
        """
        # TODO: this logic probably could be common so worth either a _method
        # or a decorator to get the file requested into the function
        file_ = self.get_file_with_digest(checksum, **digest)

        if not file_:
            # just for exception msg
            digest = _get_digest_value(checksum, **digest)
            raise ValueError("No file found in DB having %s" % str(digest))

        return self.get_urls(file_, valid_only=valid_only)

    # TODO: dichotomy since above get_file beasts return ORMs File and here by default -- url itself
    def get_urls(self, file_, valid_only=True, url_only=True):
        urls = self._query(oURL).filter_by(file_id=file_.id)
        #urls = file_.urls
        if valid_only:
            urls = [u for u in urls if u.valid]
        return [u.url for u in urls] if url_only else urls

    def _set_content_type_info(self, file_, fpath):
        pass   # TODO, implement helper under datalad.utils

    def process_file(self, fpath):
        """For a given file compute its checksums and record that information in DB

        Parameters
        ----------
        fpath: str
          Relative or full path to the file
        urls: str or list of str
          URLs to associate with this file
        repos: list of ...
          Repos where this file can be found
        special_remotes: list of ...
        checked

        Returns
        -------
        File
        """
        digests = self._digester(fpath)
        size = os.stat(fpath).st_size
        # TODO: check if we have entry known already if not, record in DB
        try:
            file_ = self._query(oFile).filter_by(**digests).one()
            # verify that we have correct size
            if file_.size != size:
                raise ValueError("File size %d differs from the previously recorded %d"
                                 % (size, file_.size))
        except NoResultFound:
            # we need to create a new one!
            file_ = self._add(oFile(size=size, **digests))
            self._set_content_type_info(file_, fpath)

        return file_


    def add_url(self, file_, url, filename=None,
                last_modified=None,
                content_type=None,
                checked=True, valid=None, invalid_reason=None):
        """Add or just update (if checked/valid) a URL associated with the file"""
        # TODO: probably would be more efficient with a proper query
        urls = {e.url: e for e in file_.urls}
        if url in urls:
            url_ = urls[url]
            if filename and url_.filename != filename:
                raise NotImplementedError(
                    "We know different file name %s for the url_ %s and no override " \
                    "is implemented ATM. Got new filename=%s"
                    % (url_.filename, url_, filename))
            # check existing file to "correspond"
            if file_.id != url_.file_id:
                raise NotImplementedError(
                    "Logic/options for reassigning url from one file (content) to another"
                )
        else:
            lgr.debug("Creating new entry for URL %s" % url)
            url_ = oURL(url=url, file_id=file_.id)
            if filename:
                url_.filename = filename
            if content_type:
                url_.content_type = content_type
            if last_modified:
                url_.content_type = content_type
            file_.urls.append(url_)
            #self._add(url_)
            # TODO: all above could be slow etc.
            # Look into better/lazy way:  http://stackoverflow.com/a/8842527

        # TODO: possibly move into a helper function, so "logic" could be reused
        # with annex repos etc
        curtime = datetime.now()
        if checked:
            url_.last_checked = curtime
            if not url_.first_checked:
                url_.first_checked = curtime

        if valid:
            url_.last_validated = curtime
            if not url_.first_validated:
                url_.first_validated = curtime
            url_.valid = True
        elif valid is None:
            # we have no information -- just pass
            pass
        else:  # must be False!
            assert valid is False
            assert invalid_reason is not None, "if not valid -- provide a reason!"
            url_.last_invalid = curtime
            url_.invalid_reason = invalid_reason
            url_.valid = False

        return url_

    # def invalidate_url(self, file_, url):
    #     for url in file_.urls:

    #
    # TODO:  after we are done torturing URLs, implement support for annex repos/special remotes
    #
    def get_key(self, key, file_=None):
        """Given possibly a string key return Key object, might need to register it within DB first"""
        if not isinstance(key, oKey):
            key_ = key
            # we need to either retrieve or create it
            try:
                key = self._query(oKey).filter_by(key=key_).one()
            except NoResultFound:
                assert (isinstance(file_, oFile))    # WE NEED A FILE!
                key = self._add(oKey(key=key_, file=file_))
        return key

    def add_key_to_repo(self, key, repo):
        key = self.get_key(key)  # to assure that we got a Key, would raise if none known yet
        raise NotImplementedError

    def add_key_to_special_remotes(self, key, special_remotes):
        raise NotImplementedError
