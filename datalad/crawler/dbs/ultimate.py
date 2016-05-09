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
from sqlalchemy import or_

from ...support.digests import Digester

import logging
from logging import getLogger
lgr = getLogger('datalad.crawler.dbs.ultimate')

LEN_TO_DIGEST = {
    32: 'md5',
    40: 'sha1',
    64: 'sha256',
    128: 'sha512'
}
KNOWN_DIGESTS = set(LEN_TO_DIGEST.values())
DEFAULT_DIGEST = "sha256"


class HashCollisionError(ValueError):
    """Exception to "celebrate" -- we ran into a hash collision.  World should skip a bit"""
    pass


class UltimateDB(object):
    """Database collating urls for the content across all handles

    Schema: TODO, but needs for sure


    - entry: checksums (MD5, SHA1, SHA256, SHA512), size
    - entry ->> URL (only "public" or internal as for content from archives, or that separate table?)
      where for each URL store
        - STR  url
        - DATE first_checked
        - DATE first_verified
        - DATE last_checked (if accessible online)
        - DATE last_verified (when verified to contain the content according to the checksums)
        - BOOL valid (if verification fails, mark as not valid, still can have last_verified)
        - DATE last_invalid (date of last check to remain invalid)
        - INT8 invalid_reason : removed, changed, forbidden?
        -? datalad_internal (e.g. for archives) or may be
        -? url_schema -- then we could easily select out datalad-archives:// later on,
           but it would duplicate information in url, so consistency burden

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

    __metaclass__ = ABCMeta

    def __init__(self, digester=None):
        self._digester = digester or Digester(list(KNOWN_DIGESTS))
        self._session = None
        self.connect()

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

    @staticmethod
    def _initiate_db(engine):
        lgr.info("Initiating Ultimate DB tables")
        return DBTable.metadata.create_all(engine)

    def __contains__(self, url):
        return self.knows_file_url(url)

    def knows_file_url(self, url):
        """Return True if DB knows about this URL (as associated with a file)"""
        return self._session.query(URL).filter_by(url=url).first() is not None

    def has_file_with_digests(self, **digests):
        assert set(digests) == KNOWN_DIGESTS, "Provide all digests for a file of interest"
        # search by default one
        try:
            digest = {DEFAULT_DIGEST: digests[DEFAULT_DIGEST]}
            file = self._session.query(File).filter_by(**digest).one()
        except NoResultFound:
            return False
        except MultipleResultsFound:
            raise HashCollisionError("??? multiple entries for %s" % str(digest))

        # otherwise check if other digests correspond
        for algo, checksum in digests.items():
            if getattr(file, algo) != checksum:
                raise HashCollisionError(
                    "%s %s != %s.  Full entries: %s, %s"
                    % (algo, getattr(file, algo), checksum, digests, file)
                )
        return True

    #@abstractmethod
    def __getitem__(self, checksum=None):
        return self.get_urls_for_digest(checksum)

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
        digest = self._get_digest_value(checksum, **digest)
        try:
            file_ = self._session.query(File).filter_by(**digest).one()
        except NoResultFound:
            return None
        # if .one fails since multiple -- we have a collision!  would be interesting to see
        # so please report if you run into one ;)
        if not file_:
            raise ValueError("No file found in DB having %s=%s" % (algo, checksum))
        urls = file_.urls
        if valid_only:
            urls = [x for x in urls if x.verified]
        return urls

    @staticmethod
    def _get_digest_value(checksum=None, **digest):
        """Just a helper so we could simply provide a value or specify which algorithm"""
        if digest:
            if len(digest) > 1 or (digest.keys()[0] not in KNOWN_DIGESTS) or checksum:
                raise ValueError(
                    "You must either specify checksum= or explicitly "
                    "one of known digests %s" % KNOWN_DIGESTS)
        else:
            try:
                digest = {LEN_TO_DIGEST[len(checksum)]: checksum}
            except:
                raise ValueError("Checksum %s of len %d has no known digest algorithm"
                                 % (checksum, len(checksum)))
                # may be at some point we would like to find one based on the leading
                # few characters of the checksum but not atm
        return digest

    def touch_url(self, entry, url, checked=False, verified=False): #last_checked=None, last_verified=None):
        """Set entry for a URL associated with an entry as checked and/or verified

        verified: bool, optional
          If True, means checked=True as well
        """
        # TODO
        pass


    def process_file(self, fpath, urls, checked=False, verified=False):
        """For a given file compute its checksums and record that information in DB

        Parameters
        ----------
        fpath: str
          Relative or full path to the file
        urls: str or list of str
          URLs to associate with this file
        """
        digests = self.get_digests(fpath)
        # TODO: check if we have entry known already if not, record in DB
        entry = None
        # TODO: check if urls are known for the entry, update accordingly not forgetting about time stamps
        for url in urls:
            self.touch_url(entry, url, checked=checked, verified=verified)
        return digests

    def get_digests(self, fpath):
        """Return digests for a file
        """
        return self._digester(fpath)

"""
I foresee functionality which would use UltimateDB to carry out various actions.
Probably best positioned outside of the DB...?

    URLsVerifier -- to check and/or verify URLs to contain the same load
      This one might want to use Status information for quick verification, which is
      stored in other DBs... Should we also store size/mtime in UltimateDB?
      Probably so -- size for each entry, mtime for each URL.  Some URLs might not provide
      reliable mtime though.
      But really to verify 100% we would need a full download

    URLsUpdater -- given an annex and db, go through the keys (all? for some files? ...) and update
      annex information on urls.

    Upon regular end of crawling we would want to use URLsUpdater to extend/update known
    information
"""

from sqlalchemy.ext.declarative import declarative_base

DBTable = declarative_base()

from datalad.utils import auto_repr

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy import Binary
# only from upcoming 1.1
#from sqlalchemy.types import JSON
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

INVALID_REASONS = ['NA', 'removed', 'changed', 'denied']

# XXX not sure when penalty comes due to our many-to-many relationships
# which might be an additional query etc... depending how/when it is done
# (e.g. if at the request of .files attribute value), we might want to exclude
# those from @auto_repr
@auto_repr
class File(DBTable):
    """
    Binds together information about the file content -- common digests and size
    """
    __tablename__ = 'file'

    id = Column(Integer, primary_key=True)
    size = Column(Integer)  # in Bytes
    # Digests
    md5 = Column(Binary(32), index=True)  # we will more frequently query by md5 and sha256 (Default) so indexing them
    sha1 = Column(Binary(40))
    sha256 = Column(Binary(64), index=True, unique=True)  # if we hit collision at this digest -- wooo
    sha512 = Column(Binary(128), unique=True)
    # Additional info from output of file
    content_type = Column(Binary(256))
    content_charset = Column(Binary(64))
    # running file -z
    content_type_extracted = Column(Binary(256))
    content_charset_extracted = Column(Binary(64))


@auto_repr
class URL(DBTable):
    """Information about URLs from which a file could be downloaded

    So it is the urls which could be associated with keys in annex.
    For git repositories serving .git/annex/objects via http (so theoretically there
    is a URL per each key), just use  `SpecialRemote(location=url, type='git')`
    """
    __tablename__ = 'url'

    id = Column(Integer, primary_key=True)
    url = Column(String)  # TODO: limit size?  probably not since even standard doesn't really... browsers usually handle up to 2048
    filename = Column(String)  # could differ from the one in URL due to content-disposition etc

    last_modified = Column(DateTime)
    content_type = Column(Binary(256))  # 127/127   RFC 6838   server might provide different one

    # just checked to be accessible
    first_checked = Column(DateTime)
    last_checked = Column(DateTime)

    # checked to contain the target load
    first_verified = Column(DateTime)
    last_verified = Column(DateTime)

    valid = Column(Boolean)
    last_invalid = Column(DateTime)
    invalid_reason = Column(Enum(*INVALID_REASONS))  #  XXX we might want to use fancy Enum class backported to 2.x?

    file_id = Column(Integer, ForeignKey('file.id'))
    # link back to the file and also allocate 1-to-many .urls in File
    file = relationship("File", backref="urls")


# Later tables establish tracking over repositories available locally or remotely
# E.g. a remote git-annex repository containing annex load would be listed as a
# SpecialRemote type=git with location pointing to e.g. http:// url from where
# annex load could be fetched if necessary.

from sqlalchemy import Table

files_to_repos = Table(
    'files_to_repos', DBTable.metadata,
    Column('file_id', Integer, ForeignKey('file.id')),
    Column('repo_id', Integer, ForeignKey('repo.id'))
)


@auto_repr
class Repo(DBTable):
    """
    Local annex repositories
    """
    __tablename__ = 'repo'

    id = Column(Integer, primary_key=True)
    location = Column(String)
    uuid = Column(Binary(36))
    bare = Column(Boolean())

    last_checked = Column(DateTime)

    valid = Column(Boolean)
    last_invalid = Column(DateTime)
    invalid_reason = Column(Enum(*INVALID_REASONS))  #  XXX we might want to use fancy Enum class backported to 2.x?

    files = relationship("File",
                         secondary=files_to_repos,
                         backref="repos")

files_to_specialremotes = Table(
    'files_to_specialremotes', DBTable.metadata,
    Column('file_id', Integer, ForeignKey('file.id')),
    Column('specialremote_id', Integer, ForeignKey('specialremote.id'))
)


@auto_repr
class SpecialRemote(DBTable):
    """
    Special annex remotes
    """
    __tablename__ = 'specialremote'

    id = Column(Integer, primary_key=True)
    location = Column(String)
    name = Column(String)
    uuid = Column(Binary(36))
    type = Column(String(256))  # unlikely to be longer:  s3, git,
    # ??? could options differ among repos for the same special remote?
    options = Column(String())  # actually a dict, so ideally we could use JSON which will be avail in 1.1
                                # for now will encode using ... smth

    last_checked = Column(DateTime)

    valid = Column(Boolean)
    last_invalid = Column(DateTime)
    invalid_reason = Column(Enum(*INVALID_REASONS))  #  XXX we might want to use fancy Enum class backported to 2.x?

    files = relationship("File",
                         secondary=files_to_specialremotes,
                         backref="specialremotes")


# TODO?  some kind of "transactions" DB which we possibly purge from time to time???


"""
engine = create_engine('sqlite:///:memory:', echo=True)
def _initiate_tables(engine):
    return DBTable.metadata.create_all(engine)


file = File(md5="a1b23")  # woohoo autorepr works!!!
url = URL(url="http://example.com", file=file)

_initiate_tables(engine)
session = Session(bind=engine)
session.add(url)
session.flush()

print file.id
print repr(file.md5), file, file.urls

print url, url.id
session.query(File).filter_by(md5='a1b23').one().urls
session.query(File).filter(or_(File.sha1==None, File.md5==None)).one()
import q; q.d()
"""