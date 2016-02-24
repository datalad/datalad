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

from ...support.digests import Digester

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
        self.digester = digester or Digester()

    @abstractmethod
    def __contains__(self, url):
        """Return True if DB knows about this URL """
        pass

    @abstractmethod
    def __getitem__(self, checksum=None, verified_only=True):  #, md5=None, sha256=None):
        """Given a checksum, return URLs where it is available from"""
        pass

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