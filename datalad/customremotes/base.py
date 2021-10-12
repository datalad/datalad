# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes to custom git-annex remotes (e.g. extraction from archives)"""

from __future__ import absolute_import

__docformat__ = 'restructuredtext'

import errno
import os
import sys

from collections import Counter

from ..support.path import (
    join as opj,
    lexists,
)

from urllib.parse import urlparse

import logging
lgr = logging.getLogger('datalad.customremotes')
lgr.log(5, "Importing datalad.customremotes.main")

from ..ui import ui
from ..support.cache import DictCache
from datalad.support.exceptions import CapturedException
from ..cmdline.helpers import get_repo_instance
from datalad.utils import (
    getargspec,
)

URI_PREFIX = "dl"
SUPPORTED_PROTOCOL = 1

DEFAULT_COST = 100
DEFAULT_AVAILABILITY = "LOCAL"


class AnnexRemoteQuit(Exception):
    pass


def get_function_nargs(f):
    while hasattr(f, 'wrapped'):
        f = f.wrapped
    argspec = getargspec(f)
    assert not argspec.keywords, \
        "ATM we have none defined with keywords, so disabling having them"
    if argspec.varargs:
        # Variable number of arguments
        return -1
    else:
        assert argspec.args, "ATM no static methods"
        assert argspec.args[0] == "self"
        return len(argspec.args) - 1


class AnnexCustomRemote(object):
    """Base class to provide custom special remotes for git-annex

    Implements git-annex special custom remotes protocol described
    at
    http://git-annex.branchable.com/design/external_special_remote_protocol/
    """

    # Must be defined in subclasses.  There is no classlevel properties, so leaving as this for now

    CUSTOM_REMOTE_NAME = None  # if None -- no additional custom remote name
    SUPPORTED_SCHEMES = ()

    COST = DEFAULT_COST
    AVAILABILITY = DEFAULT_AVAILABILITY

    def __init__(self, path=None, cost=None, fin=None, fout=None):  # , availability=DEFAULT_AVAILABILITY):
        """
        Parameters
        ----------
        path : string, optional
            Path to the repository for which this custom remote is serving.
            Usually this class is instantiated by a script which runs already
            within that directory, so the default is to point to current
            directory, i.e. '.'
        fin:
        fout:
            input/output streams.  If not specified, stdin, stdout used
        """
        from ..support.annexrepo import AnnexRepo

        # Custom remotes correspond to annex via stdin/stdout
        self.fin = fin or sys.stdin
        self.fout = fout or sys.stdout

        self.repo = get_repo_instance(class_=AnnexRepo) \
            if not path \
            else AnnexRepo(path, create=False, init=False)

        self.path = self.repo.path

        self._progress = 0  # transmission to be reported back if available
        if cost is None:
            cost = self.COST
        self.cost = cost
        #self.availability = availability.upper()
        assert(self.AVAILABILITY.upper() in ("LOCAL", "GLOBAL"))

        # To signal whether we are in the loop and e.g. could correspond to annex
        self._in_the_loop = False
        self._contentlocations = DictCache(size_limit=100)  # TODO: config ?

        # instruct annex backend UI to use this remote
        if ui.backend == 'annex':
            ui.set_specialremote(self)

        # Delay introspection until the first instance gets born
        # could in principle be done once in the metaclass I guess
        self.__class__._introspect_req_signatures()

        # OPT: a counter to increment upon successful encounter of the scheme
        # (ATM only in gen_URLS but later could also be used in other requests).
        # This would allow to consider schemes in order of decreasing success instead
        # of arbitrary hardcoded order
        self._scheme_hits = Counter({s: 0 for s in self.SUPPORTED_SCHEMES})

    @classmethod
    def _introspect_req_signatures(cls):
        """
        Check req_ methods to figure out expected number of arguments
        See https://github.com/datalad/datalad/issues/1727
        """
        if hasattr(cls, '_req_nargs'):
            # We have already figured it out for this class
            return
        cls._req_nargs = {
            m[4:]: get_function_nargs(getattr(cls, m))
            for m in dir(cls)
            if m.startswith('req_')
        }

    @classmethod
    def _get_custom_scheme(cls, prefix):
        """Helper to generate custom datalad URL prefixes
        """
        # prefix which will be used in all URLs supported by this custom remote
        # https://tools.ietf.org/html/rfc2718 dictates "URL Schemes" standard
        # 2.1.2   suggests that we do use // since all of our URLs will define
        #         some hierarchical structure.  But actually since we might encode
        #         additional information (such as size) into the URL, it will not be
        #         strictly conforming it. Thus we will not use //
        return "%s+%s" % (URI_PREFIX, prefix)  # if .PREFIX else '')

    # Helpers functionality

    def get_contentlocation(self, key, absolute=False, verify_exists=True):
        """Return (relative to top or absolute) path to the file containing the key

        This is a wrapper around AnnexRepo.get_contentlocation which provides caching
        of the result (we are asking the location for the same archive key often)
        """
        if key not in self._contentlocations:
            fpath = self.repo.get_contentlocation(key, batch=True)
            if fpath:  # shouldn't store empty ones
                self._contentlocations[key] = fpath
        else:
            fpath = self._contentlocations[key]
            # but verify that it exists
            if verify_exists and not lexists(opj(self.path, fpath)):
                # prune from cache
                del self._contentlocations[key]
                fpath = ''

        if absolute and fpath:
            return opj(self.path, fpath)
        else:
            return fpath

    #
    # Communication with git-annex
    #
    def send(self, *args):
        """Send a message to git-annex

        Parameters
        ----------
        `*args`: list of strings
           arguments to be joined by a space and passed to git-annex
        """
        msg = " ".join(map(str, args))
        # Sanitize since there must be no new lines
        msg = msg.replace(os.linesep, r'\n')
        if not self._in_the_loop:
            lgr.debug("We are not yet in the loop, thus should not send to annex"
                      " anything.  Got: %s" % msg.encode())
            return
        try:
            self.heavydebug("Sending %r" % msg)
            self.fout.write(msg + "\n")  # .encode())
            self.fout.flush()
        except IOError as exc:
            lgr.debug("Failed to send due to %s", exc)
            if exc.errno == errno.EPIPE:
                self.stop()
            else:
                raise exc

    def send_unsupported(self, msg=None):
        """Send UNSUPPORTED-REQUEST to annex and log optional message in our log
        """
        if msg:
            lgr.debug(msg)
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
        l = self.fin.readline().rstrip(os.linesep)
        msg = l.split(None, n)
        if req and ((not msg) or (req != msg[0])):
            # verify correct response was given
            self.send_unsupported(
                "Expected %r, got a line %r.  Ignoring" % (req, l)
            )
            return None
        self.heavydebug("Received %r" % (msg,))
        return msg

    # TODO: see if we could adjust the "originating" file:line, because
    # otherwise they are all reported from main.py:117 etc
    def heavydebug(self, msg, *args, **kwargs):
        lgr.log(4, msg, *args, **kwargs)

    # Since protocol allows for some messaging back, let's duplicate to lgr
    def debug(self, msg):
        lgr.debug(msg)
        self.send("DEBUG", msg)

    def error(self, msg, annex_err="ERROR"):
        lgr.error(msg)
        self.send(annex_err, msg)

    def info(self, msg):
        lgr.info(msg)
        self.send('INFO', msg)

    def progress(self, bytes):
        bytes = int(bytes)
        if self._progress != bytes:
            self.send("PROGRESS", bytes)

    def main(self):
        """Interface to the command line tool"""

        try:
            self._in_the_loop = True
            self._loop()
        except AnnexRemoteQuit:
            pass  # no harm
        except KeyboardInterrupt:
            self.stop("Interrupted by user")
        except Exception as e:
            self.stop(str(e))
        finally:
            self._in_the_loop = False

    def stop(self, msg=None):
        lgr.debug("Stopping communications of %s%s" %
                 (self, ": %s" % msg if msg else ""))
        raise AnnexRemoteQuit(msg)

    def _loop(self):
        """The main loop
        """

        self.send("VERSION", SUPPORTED_PROTOCOL)

        while True:
            l = self.read(n=1)

            if l is not None and not l:
                # empty line: exit
                self.stop()
                return

            req, req_load = l[0], l[1:]
            method = getattr(self, "req_%s" % req, None)
            if not method:
                self.send_unsupported(
                    "We have no support for %s request, part of %s response"
                    % (req, l)
                )
                continue

            req_nargs = self._req_nargs[req]
            if req_load and req_nargs > 1:
                assert len(req_load) == 1, "Could be only one due to n=1"
                # but now we need to slice it according to the respective req
                # We assume that at least it shouldn't start with a space
                # since str.split would get rid of it as well, and then we should
                # have used re.split(" ", ...)
                req_load = req_load[0].split(None, req_nargs - 1)

            try:
                method(*req_load)
            except Exception as e:
                ce = CapturedException(e)
                self.error("Problem processing %r with parameters %r: %s"
                           % (req, req_load, ce))
                from traceback import format_exc
                lgr.error("Caught exception detail: %s", format_exc())

    def req_INITREMOTE(self, *args):
        """Initialize this remote. Provides high level abstraction.

        Specific implementation should go to _initialize
        """

        try:
            self._initremote(*args)
        except Exception as e:
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
        except Exception as e:
            self.error("Failed to prepare %s due to %s" % (self, e),
                       "PREPARE-FAILURE")
        else:
            self.send("PREPARE-SUCCESS")

        self.debug("Encodings: filesystem %s, default %s"
                   % (sys.getfilesystemencoding(), sys.getdefaultencoding()))

    def req_EXPORTSUPPORTED(self):
        self.send(
            'EXPORTSUPPORTED-SUCCESS'
            if hasattr(self, 'req_EXPORT')
            else 'EXPORTSUPPORTED-FAILURE'
        )

    ## define in subclass if EXPORT is supported
    # def req_EXPORT(self, name):
    #   pass

    def req_GETCOST(self):
        self.send("COST", self.cost)

    def req_GETAVAILABILITY(self):
        self.send("AVAILABILITY", self.AVAILABILITY.upper())

    def req_CLAIMURL(self, url):
        scheme = urlparse(url).scheme
        if scheme in self.SUPPORTED_SCHEMES:
            self.debug("Claiming url %r" % url)
            self.send("CLAIMURL-SUCCESS")
        else:
            self.debug("Not claiming url %s" % url)
            self.send("CLAIMURL-FAILURE")

    # TODO: we should unify what to be overridden and some will provide CHECKURL

    def req_TRANSFER(self, cmd, key, file):
        if cmd in ("RETRIEVE",):
            lgr.debug("%s key %s into/from %s", cmd, key, file)  # was INFO level
            try:
                self._transfer(cmd, key, file)
            except Exception as exc:
                ce = CapturedException(exc)
                self.send(
                    "TRANSFER-FAILURE %s %s %s" % (cmd, key, ce)
                )
        else:
            self.send_unsupported(
                "Received unsupported by our TRANSFER command %s" % cmd
            )

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

    def req_WHEREIS(self, key):
        """Added in 5.20150812-17-g6bc46e3

        provide any information about ways to access the content of a key stored in it,
        such as eg, public urls. This will be displayed to the user by eg,
        git annex whereis. The remote replies with WHEREIS-SUCCESS or WHEREIS-FAILURE.
        Note that users expect git annex whereis to run fast, without eg, network access.
        This is not needed when SETURIPRESENT is used, since such uris are automatically
        displayed by git annex whereis.

        WHEREIS-SUCCESS String
            Indicates a location of a key. Typically an url, the string can be anything
            that it makes sense to display to the user about content stored in the special
            remote.
        WHEREIS-FAILURE
            Indicates that no location is known for a key.
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
    def get_DIRHASH(self, key, full=False):
        """Gets a two level hash associated with a Key.

        Parameters
        ----------
        full: bool, optional
          If True, would spit out full DIRHASH path, i.e. with a KEY/ directory

        Something like "abc/def". This is always the same for any given Key, so
        can be used for eg, creating hash directory structures to store Keys in.
        """
        self.send("DIRHASH", key)
        val = self.read("VALUE", 1)[1]
        if full:
            return opj(self.path, val, key)
        else:
            return val

    def gen_URLS(self, key):
        """Yield URL(s) associated with a Key.

        """
        nurls = 0
        for scheme, _ in self._scheme_hits.most_common():
            scheme_ = scheme + ":"
            self.send("GETURLS", key, scheme_)
            # we need to first to slurp in all for a given SCHEME
            # since annex would be expecting to send its final empty VALUE
            scheme_urls = []
            while True:
                url = self.read("VALUE", 1)
                if not url or len(url) <= 1:
                    # so there were no URL output, we must be done
                    break
                url = url[1:]
                if url:
                    assert(len(url) == 1)
                    nurls += 1
                    scheme_urls.append(url[0])
                else:
                    break
            if scheme_urls:
                # note: generator would cease to exist thus not asking
                # for URLs for other schemes if this scheme is good enough
                self._scheme_hits[scheme] += 1
                for url in scheme_urls:
                    yield url

        self.heavydebug("Got %d URL(s) for key %s", nurls, key)

    def get_URLS(self, key):
        """Gets URL(s) associated with a Key.

        Use a generator gen_URLS where possible.
        This one should be deprecated in 0.15.
        """
        return list(self.gen_URLS(key))

    # TODO: test on annex'es generated with those new options e.g.-c annex.tune.objecthash1=true
    #def get_GETCONFIG SETCONFIG  SETCREDS  GETCREDS  GETUUID  GETGITDIR  SETWANTED  GETWANTED
    #SETSTATE GETSTATE SETURLPRESENT  SETURLMISSING


def generate_uuids():
    """Generate UUIDs for our remotes. Even though quick, for consistency pre-generated and recorded in consts.py"""
    import uuid
    return {
        remote: str(uuid.uuid5(uuid.NAMESPACE_URL, 'http://datalad.org/specialremotes/%s' % remote))
        for remote in {'datalad', 'datalad-archives'}
    }


def init_datalad_remote(repo, remote, encryption=None, autoenable=False, opts=[]):
    """Initialize datalad special remote"""
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
    lgr.info("Initiating special remote %s", remote)
    remote_opts = [
        'encryption=%s' % str(encryption).lower(),
        'type=external',
        'autoenable=%s' % str(bool(autoenable)).lower(),
        'externaltype=%s' % remote
    ]
    # use unique uuid for our remotes
    # This should help with merges of disconnected repos etc
    # ATM only datalad/datalad-archives is expected,
    # so on purpose getitem
    remote_opts.append('uuid=%s' % DATALAD_SPECIAL_REMOTES_UUIDS[remote])
    return repo.init_remote(remote, remote_opts + opts)


def ensure_datalad_remote(repo, remote=None,
                          encryption=None, autoenable=False):
    """Initialize and enable datalad special remote if it isn't already.

    Parameters
    ----------
    repo : AnnexRepo
    remote : str, optional
        Special remote name. This should be one of the values in
        datalad.consts.DATALAD_SPECIAL_REMOTES_UUIDS and defaults to
        datalad.consts.DATALAD_SPECIAL_REMOTE.
    encryption, autoenable : optional
        Passed to `init_datalad_remote`.
    """
    from datalad.consts import DATALAD_SPECIAL_REMOTE
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS

    remote = remote or DATALAD_SPECIAL_REMOTE

    uuid = DATALAD_SPECIAL_REMOTES_UUIDS.get(remote)
    if not uuid:
        raise ValueError("'{}' is not a known datalad special remote: {}"
                         .format(remote,
                                 ", ".join(DATALAD_SPECIAL_REMOTES_UUIDS)))
    name = repo.get_special_remotes().get(uuid, {}).get("name")

    if not name:
        from datalad.consts import DATALAD_SPECIAL_REMOTE

        init_datalad_remote(repo, DATALAD_SPECIAL_REMOTE,
                            encryption=encryption, autoenable=autoenable)
    elif repo.is_special_annex_remote(name, check_if_known=False):
        lgr.debug("datalad special remote '%s' is already enabled", name)
    else:
        lgr.info("datalad special remote '%s' found. Enabling", name)
        repo.enable_remote(name)


lgr.log(5, "Done importing datalad.customremotes.main")
