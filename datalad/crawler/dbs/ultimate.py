# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to provide Ultimate DB to store URLs, checksums, etc to cross-pollinate across handles/sources"""

from abc import ABCMeta, abstractmethod, abstractproperty

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.engine.reflection import Inspector

from ...support.digests import Digester

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
DEFAULT_ALGO = "sha256"


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
                "one of known digests %s" % KNOWN_ALGO)
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
        if auto_connect:
            self.connect()

    # XXX or should this be reserved for checksums?
    #  probably so since __getitem__ operates on checksums -- TODO
    def __contains__(self, url):
        return self.has_file_with_url(url)

    #@abstractmethod
    def __getitem__(self, checksum=None):
        return self.get_urls_for_digest(checksum)

    @staticmethod
    def _initiate_db(engine):
        lgr.info("Initiating Ultimate DB tables")
        return DBTable.metadata.create_all(engine)

    def _handle_collision(self, digest):
        raise HashCollisionError("??? multiple entries for %s" % str(digest))

    def connect(self):
        # TODO: config.crawler.db stuff
        engine = create_engine('sqlite:///:memory:')
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

    def has_file_with_url(self, url):
        """Return True if DB knows about this URL (as associated with a file)"""
        return self._session.query(URL.id).filter_by(url=url).first() is not None

    def has_file_with_digests(self, **digests):
        # XXX may be relax allowing for arbitrary set of digests or just a checksum being provided
        assert set(digests) == KNOWN_ALGO, "Provide all digests for a file of interest"
        # search by default one
        try:
            digest = {DEFAULT_ALGO: digests[DEFAULT_ALGO]}
            file_ = self._session.query(File).filter_by(**digest).one()
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

    def has_file_with_digest(self, *args, **kwargs):
        # cheat/reuse for now
        try:
            # underlying function returns
            return self.get_urls_for_digest(*args, **kwargs) is not None
        except HashCollisionError:
            raise  # just reraise for now
        # except:
        #     return False

    def get_urls_for_digest(self, checksum=None, valid_only=True, **digest):
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
        digest = _get_digest_value(checksum, **digest)
        try:
            file_ = self._session.query(File.urls).filter_by(**digest).one()
        except NoResultFound:
            return None
        except MultipleResultsFound:
            return self._handle_collision(digest)

        # if .one fails since multiple -- we have a collision!  would be interesting to see
        # so please report if you run into one ;)
        if not file_:
            raise ValueError("No file found in DB having %s" % str(digest))
        urls = file_.urls
        if valid_only:
            urls = [u for u in urls if u.valid]
        return urls

    # XXX would be somewhat duplicate heavy API of process_file ...
    # may be could be merged/RFed to share functionality
    def _touch_file(self, file_id, url, checked=True, valid=False): #last_checked=None, last_validated=None):
        """Set entry for a URL associated with an entry as checked and optionally as valid

        By default assumes that url was checked to exist but was not valid to
        contain exact "entry"

        Parameters
        ----------
        file_id: ????
          as in DB
        url : str
        checked
        valid: bool, optional
          If True, means checked=True as well
        """
        if valid:
            assert(checked)
        # TODO
        pass


    def process_file(self, fpath, urls=None, repos=None, special_remotes=None, checked=False, valid=False):
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
        """
        digests = self.get_file_digests(fpath)
        # TODO: check if we have entry known already if not, record in DB
        try:
            file_ = self._session.query(File).filter_by(**digests).one()
        except NoResultFound:
            # we need to create a new one!
            file_ = File(**digests)
            self._session.add(file_)
            self._session.commit()
        # TODO: check if urls are known for the entry, update accordingly not forgetting about time stamps
        for url in urls or []:
            #self.touch_url(entry, url, checked=checked, valid=valid)
            pass
        return digests

    def get_file_digests(self, fpath):
        """Return digests for a file
        """
        return self._digester(fpath)
