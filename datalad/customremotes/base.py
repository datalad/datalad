# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes to custom git-annex remotes (e.g. extraction from archives)"""

__docformat__ = 'restructuredtext'

import errno
import os
import sys

from os.path import exists, join as opj

import logging
lgr = logging.getLogger('datalad.customremotes')

#lgr.setLevel(1) # DEBUGGING TODO: remove

URI_PREFIX = "dl+"
SUPPORTED_PROTOCOL = 1

DEFAULT_COST = 100
DEFAULT_AVAILABILITY = "local"


class AnnexRemoteQuit(Exception):
    pass

class AnnexCustomRemote(object):
    """Base class to provide custom special remotes for git-annex

    Implements git-annex special custom remotes protocol described
    at
    http://git-annex.branchable.com/design/external_special_remote_protocol/
    """

    AVAILABILITY = DEFAULT_AVAILABILITY

    def __init__(self, cost=DEFAULT_COST): # , availability=DEFAULT_AVAILABILITY):
        # Custom remotes correspond to annex via stdin/stdout
        self.fin = sys.stdin
        self.fout = sys.stdout

        self._progress = 0 # transmission to be reported back if available
        self.cost = cost
        #self.availability = availability.upper()
        assert(self.AVAILABILITY.upper() in ("LOCAL", "GLOBAL"))

        # prefix which will be used in all URLs supported by this custom remote
        self.url_prefix = "%s%s:" % (URI_PREFIX, self.PREFIX)

    @property
    def PREFIX(self):
        """Just a helper to guarantee that PREFIX gets assigned in derived class
        """
        raise ValueError("Each derived class should carry its own PREFIX")

    def send(self, *args):
        """Send a message to git-annex

        Parameters
        ----------
        *args: list of strings
           arguments to be joined by a space and passed to git-annex
        """
        try:
            msg = " ".join(map(str, args))
            self.heavydebug("Sending %r" % msg)
            self.fout.write("%s\n" % msg)
            self.fout.flush()
        except IOError as exc:
            lgr.debug("Failed to send due to %s" % str(exc))
            if exc.errno == errno.EPIPE:
                self.stop()
            else:
                raise exc

    def send_unsupported(self):
        self.send("UNSUPPORTED-REQUEST")

    def read(self, req=None, n=1):
        """Read a message from git-annex

        Parameters
        ----------

        req : string, optional
           Expected request - first msg of the response
        n : int
           Number of response elements after first msg
        """
        # TODO: should we strip or should we not? verify how annex would deal
        # with filenames starting/ending with spaces - encoded?
        # Split right away
        l = self.fin.readline().rstrip('\n')
        msg = l.split(None, n)
        if req and (req != msg[0]):
            # verify correct response was given
            self.error("Expected %r, got %r.  Ignoring" % (resp, msg[0]))
            return None
        self.heavydebug("Received %r" % (msg,))
        return msg

    def heavydebug(self, msg):
        lgr.log(1, msg)

    # Since protocol allows for some messaging back, let's duplicate to lgr
    def debug(self, msg):
        self.send("DEBUG", msg)
        lgr.debug(msg)

    def error(self, msg, annex_err="ERROR"):
        self.send(annex_err, msg)
        lgr.error(msg)

    def progress(self, perc):
        perc = int(perc)
        if self._progress != perc:
            self.send("PROGRESS", perc)


    def main(self):
        """Interface to the command line tool"""

        try:
            self._loop()
        except KeyboardInterrupt:
            self.stop("Interrupted by user")

    def stop(self, msg=None):
        lgr.info("Stopping communications of %s%s" %
                 (self, ": " % msg if msg else ""))
        raise AnnexRemoteQuit(msg)

    def _loop(self):

        self.send("VERSION", SUPPORTED_PROTOCOL)

        while True:
            l = self.read()

            if l is not None and not l:
                # empty line: exit
                return

            req, req_load = l[0], l[1:]

            method = getattr(self, "req_%s" % req, None)
            if method:
                try:
                    method(*req_load)
                except Exception, e:
                    self.error("Problem processing request %r with parameters %r: %s"
                                % (req, req_load, e))
            else:
                self.error("We have no support for %s request, part of %s response"
                           % (req, l))
                self.send("UNSUPPORTED-REQUEST")


    def req_INITREMOTE(self, *args):
        """Initialize this remote. Provides high level abstraction.

        Specific implementation should go to _initialize
        """

        try:
            self._initremote(*args)
        except Exception, e:
            self.error("Failed to initialize %s due to %s" % (self, e),
                       "INITREMOTE-FAILURE")
        else:
            self.send("INITREMOTE-SUCCESS")


    def req_PREPARE(self, *args):
        """Prepare "to deliver". Provides high level abstraction

         Specific implementation should go to _prepare
         """
        try:
            self._prepare(*args)
        except Exception, e:
            self.error("Failed to prepare %s due to %s" % (self, e),
                       "PREPARE-FAILURE")
        else:
            self.send("PREPARE-SUCCESS")

    def req_GETCOST(self):
        self.send("COST", self.cost)

    def req_GETAVAILABILITY(self):
        self.send("AVAILABILITY", self.AVAILABILITY.upper())

    def req_CLAIMURL(self, url):
        if url.startswith(self.url_prefix):
            self.debug("Claiming url %r" % url)
            self.send("CLAIMURL-SUCCESS")
        else:
            self.debug("Not claiming url %s" % url)
            self.send("CLAIMURL-FAILURE")

    # TODO: we should unify what to be overriden and some will provide CHECKURL

    def req_TRANSFER(self, cmd, key, file):
        if cmd in ("STORE", "RETRIEVE"):
            lgr.info("%s key %s into/from %s" % (cmd, key, file))
            self._transfer(cmd, key, file)
        else:
            self.error("Retrieved unsupported for TRANSFER command %s" % cmd)
            self.send_unsupported()

    # Specific implementations to be provided in derived classes when necessary

    def req_CHECKURL(self, url):
        """
        The remote replies with one of CHECKURL-FAILURE, CHECKURL-CONTENTS, or CHECKURL-MULTI.
        CHECKURL-CONTENTS Size|UNKNOWN Filename
            Indicates that the requested url has been verified to exist.
            The Size is the size in bytes, or use "UNKNOWN" if the size could not be determined.
            The Filename can be empty (in which case a default is used), or can specify a filename that is suggested to be used for this url.
        CHECKURL-MULTI Url Size|UNKNOWN Filename ...
            Indicates that the requested url has been verified to exist, and contains multiple files, which can each be accessed using their own url.
            Note that since a list is returned, neither the Url nor the Filename can contain spaces.
        CHECKURL-FAILURE
            Indicates that the requested url could not be accessed.
        """
        self.send_unsupported()

    def req_CHECKPRESENT(self, key):
        """
        CHECKPRESENT-SUCCESS Key
            Indicates that a key has been positively verified to be present in the remote.
        CHECKPRESENT-FAILURE Key
            Indicates that a key has been positively verified to not be present in the remote.
        CHECKPRESENT-UNKNOWN Key ErrorMsg
            Indicates that it is not currently possible to verify if the key is present in the remote. (Perhaps the remote cannot be contacted.)
        """
        raise NotImplementedError()

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned if the remote didn't have the key at the point removal was requested.
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        raise NotImplementedError()

    def _transfer(self, cmd, key, file):
        raise NotImplementedError()

    def _initremote(self, *args):
        """Custom initialization of the special custom remote."""
        pass

    def _prepare(self, *args):
        """Prepare special custom remote.  To be overridden"""
        pass

    # some requests we can send out
    def get_DIRHASH(self, key):
        """Gets a two level hash associated with a Key.

        Something like "abc/def". This is always the same for any given Key, so
        can be used for eg, creating hash directory structures to store Keys in.
        """
        self.send("DIRHASH", key)
        return self.read("VALUE", 1)[1]

    def get_URLS(self, key):
        """Gets URL(s) associated with a Key.

        """
        self.send("DIRHASH", key, self.url_prefix)
        urls = []
        while True:
            url = self.read("VALUE", 1)[1]
            if url:
                urls.append(url)
            else:
                break
        return urls

    def _get_key_dir(self, key):
        """Gets a full path to the directory containing the key
        """
        return opj('.git', 'annex', 'objects', self.get_DIRHASH(key))

    def _get_key_path(self, key):
        """Gets a full path to the key"""
        self.heavydebug("Key path: %s" % opj(self._get_key_dir(key), key))
        return opj(self._get_key_dir(key), key)

    # TODO: test on annex'es generated with those new options e.g.-c annex.tune.objecthash1=true
    #def get_GETCONFIG SETCONFIG  SETCREDS  GETCREDS  GETUUID  GETGITDIR  SETWANTED  GETWANTED
    #SETSTATE GETSTATE SETURLPRESENT  SETURLMISSING


from datalad.cmd import Runner
from datalad.tests.utils import rmtree # improved for tricky permissions. TODO: move
import tempfile

class AnnexTarballCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives also under annex control

    """

    PREFIX = "tarball"
    AVAILABILITY = "local"

    def __init__(self, *args, **kwargs):
        super(AnnexTarballCustomRemote, self).__init__(*args, **kwargs)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one
        self._last_url = None # for heuristic to choose among multiple URLs
        self.runner = Runner()
        self._init_cache()

    def __del__(self):
        self._clean_cache()

    # TODO: make caching persistent across sessions/runs, with cleanup
    # TODO: extract under .git/annex/tmp so later on annex unused could clean it
    #       all up
    # TODO:  urlencode file names in the url while adding/decode upon retrieval
    def _init_cache(self):
        self._cache_dir = tempfile.mkdtemp(dir=opj('.git', 'datalad', 'tmp'))
        self.debug("Cleaning up the cache")
        if not exists(self._cache_dir):
            os.makedirs(self._cache_dir)

    def _clean_cache(self):
        self.debug("Cleaning up the cache")
        if exists(self._cache_dir):
            rmtree(self._cache_dir)


    # could well be class method
    def _parse_url(self, url):
        key, file = url[len(self.url_prefix):].split('/', 1)
        return key, file

    # Helper methods
    def _get_url(self, key):
        """Given a key, figure out the URL

        Raises
        ------
        ValueError
            If could not figure out any URL
        """
        urls = self.get_URLS(key)
        if not urls:
            raise ValueError("Do not have any URLs for %s" % key)
        elif len(urls) == 1:
            return urls[0]
        else: # multiple
            if self._last_url and self._last_url in urls:
                return self._last_url
            else:
                return urls[0] # just the first one

    def _get_key_file(self, key):
        """Given a key, figure out target archive key, and file within archive
        """
        url = self._get_url(key)
        return self._parse_url(url)

    # Protocol implementation
    def req_CHECKURL(self, url):
        """
        The remote replies with one of CHECKURL-FAILURE, CHECKURL-CONTENTS, or CHECKURL-MULTI.
        CHECKURL-CONTENTS Size|UNKNOWN Filename
            Indicates that the requested url has been verified to exist.
            The Size is the size in bytes, or use "UNKNOWN" if the size could not be determined.
            The Filename can be empty (in which case a default is used), or can specify a filename that is suggested to be used for this url.
        CHECKURL-MULTI Url Size|UNKNOWN Filename ...
            Indicates that the requested url has been verified to exist, and contains multiple files, which can each be accessed using their own url.
            Note that since a list is returned, neither the Url nor the Filename can contain spaces.
        CHECKURL-FAILURE
            Indicates that the requested url could not be accessed.
        """
        # TODO:  what about those MULTI and list to be returned?
        #  should we return all filenames or keys within archive?
        #  only if just archive portion of url is given or the one pointing to specific file?
        lgr.debug("Current directory: %s, url: %s" % (os.getcwd(), url))
        key, file = self._parse_url(url)
        if exists(self._get_key_path(key)):
            self.send("CHECKURL-CONTENTS", "UNKNOWN")
        else:
            # TODO: theoretically we should first check if key is available from
            # any remote to know if file is available
            self.send("CHECKURL-FAILURE")
        self._last_url = url

    def req_CHECKPRESENT(self, key):
        """Check if copy is available -- TODO: just proxy the call to annex for underlying tarball

        CHECKPRESENT-SUCCESS Key
            Indicates that a key has been positively verified to be present in the remote.
        CHECKPRESENT-FAILURE Key
            Indicates that a key has been positively verified to not be present in the remote.
        CHECKPRESENT-UNKNOWN Key ErrorMsg
            Indicates that it is not currently possible to verify if the key is present in the remote. (Perhaps the remote cannot be contacted.)
        """
        # TODO: so we need to maintain mapping from urls to keys.  Then
        # we could even store the filename within archive
        # Otherwise it is unrealistic to even require to recompute key if we knew the backend etc
        lgr.debug("VERIFYING key %s" % key)
        key, file = self._get_key_file(key)
        if exists(self.get_key_path(key)):
            self.send("CHECKPRESENT-SUCCESS", key)
            self._last_url = url
        else:
            # TODO: proxy the same to annex itself to verify check for archive.
            # If archive is no longer available -- then CHECKPRESENT-FAILURE
            self.send("CHECKPRESENT-UNKNOWN", key)
        raise NotImplementedError()

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned if the remote didn't have the key at the point removal was requested.
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        # TODO: proxy query to the underlying tarball under annex that if
        # tarball was removed (not available at all) -- report success,
        # otherwise failure (current the only one)
        key, file = self._get_key_file(key)
        if False: #TODO: proxy, checking present of local tarball is not sufficient  not exists(self.get_key_path(key)):
            self.send("REMOVE-SUCCESS", key)
        else:
            self.send("REMOVE-FAILURE", key,
                      "Cannot remove from the present tarball")

    def _transfer(self, cmd, key, file):

        akey, afile = self._get_key_file(key)
        akey_file = self._get_key_file(akey)

        if not exists(akey_file):
            # retrieve the key using annex
            try:
                self.runner(["git", "annex", "get", akey])
                assert(exists(akey_file))
            except Exception, e:
                self.error("Failed to fetch %{akey}s containing %{key}s: %{e}s"
                           % locals())
                return

        #

        #self.send('TRANSFER-SUCCESS', 'STORE', key)
        pass