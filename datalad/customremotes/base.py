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

from os.path import exists, join as opj, basename, realpath, dirname
from traceback import format_exc

from ..cmd import Runner

import logging


lgr = logging.getLogger('datalad.customremotes')

URI_PREFIX = "dl+"
SUPPORTED_PROTOCOL = 1

DEFAULT_COST = 100
DEFAULT_AVAILABILITY = "local"

class AnnexRemoteQuit(Exception):
    pass

class AnnexExchangeProtocol(object):
    """A little helper to protocol interactions of custom remote with annex
    """

    HEADER = r"""#!/bin/bash

set -e

# Gets a VALUE response and stores it in $RET
report () {
    echo "$@" >&2
}

recv () {
    read resp
    #resp=${resp%\n}
    target="$@"
    if [ "$resp" != "$target" ]; then
        report "! exp $target"
        report "  got $resp"
    else
        report "+ got $resp"
    fi
}

send () {
    echo "$@"
    report "sent $@"
}

"""

    def __init__(self, repopath, url_prefix):
        self.repopath = repopath
        self.url_prefix = url_prefix
        self._file = None
        self._initiated = False

    def initiate(self):
        if self._initiated:
            return
        self._initiated = True
        d = opj(self.repopath, '.git', 'bin')
        if not exists(d):
            os.makedirs(d)

        self._file = _file = \
            opj(d, 'git-annex-remote-' + self.url_prefix.rstrip(':'))

        if exists(_file):
            lgr.debug("Commenting out previous entries")
            # comment out all the past entries
            with open(_file) as f:
                entries = f.readlines()
            for i in xrange(len(self.HEADER.split(os.linesep)), len(entries)):
                e = entries[i]
                if e.startswith('recv ') or e.startswith('send '):
                    entries[i] = '#' + e
            with open(_file, 'w') as f:
                f.write(''.join(entries))
            return # nothing else to be done

        lgr.debug("Initiating protocoling."
                      "cd %s; vim %s"
                      % (realpath(self.repopath), _file[len(self.repopath)+1:]))
        with open(_file, 'a') as f:
            f.write(self.HEADER)
        os.chmod(_file, 0755)

    def write_section(self, cmd):
        self.initiate()
        with open(self._file, 'a') as f:
            f.write('%s### %s%s' % (os.linesep, cmd, os.linesep))
        lgr.error("New section in the protocol: "
                      "cd %s; PATH=%s:$PATH %s"
                      % (realpath(self.repopath),
                         dirname(self._file),
                         cmd))


    def write_entries(self, entries):
        self.initiate()
        with open(self._file, 'a') as f:
            f.write(os.linesep.join(entries + ['']))

    def __iadd__(self, entry):
        self.initiate()
        with open(self._file, 'a') as f:
            f.write(entry + os.linesep)
        return self


class AnnexCustomRemote(object):
    """Base class to provide custom special remotes for git-annex

    Implements git-annex special custom remotes protocol described
    at
    http://git-annex.branchable.com/design/external_special_remote_protocol/
    """

    AVAILABILITY = DEFAULT_AVAILABILITY

    def __init__(self, path='.', cost=DEFAULT_COST): # , availability=DEFAULT_AVAILABILITY):
        """
        Parameters
        ----------
        path : string, optional
            Path to the repository for which this custom remote is serving.
            Usually this class is instantiated by a script which runs already
            within that directory, so the default is to point to current
            directory, i.e. '.'
        """
        # TODO: probably we shouldn't have runner here but rather delegate
        # to AnnexRepo's functionality
        self.runner = Runner()

        # Custom remotes correspond to annex via stdin/stdout
        self.fin = sys.stdin
        self.fout = sys.stdout

        self.path = path

        self._progress = 0 # transmission to be reported back if available
        self.cost = cost
        #self.availability = availability.upper()
        assert(self.AVAILABILITY.upper() in ("LOCAL", "GLOBAL"))

        # prefix which will be used in all URLs supported by this custom remote
        self.url_prefix = "%s%s:" % (URI_PREFIX, self.PREFIX)

        # To signal either we are in the loop and e.g. could correspond to annex
        self._in_the_loop = False
        self._protocol = AnnexExchangeProtocol(self.path, self.url_prefix) \
                         if os.environ.get('DATALAD_PROTOCOL_REMOTE') \
                         else None

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
        msg = " ".join(map(str, args)).encode()
        if not self._in_the_loop:
            lgr.debug("We are not yet in the loop, thus should not send to annex"
                     " anything.  Got: %s" % msg)
            return
        try:
            self.heavydebug("Sending %r" % msg)
            self.fout.write("%s\n" % msg)
            self.fout.flush()
            if self._protocol is not None:
                self._protocol += "send %s" % msg
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
        l = self.fin.readline().rstrip(os.linesep)
        if self._protocol is not None:
            self._protocol += "recv %s" % l
        msg = l.split(None, n)
        if req and (req != msg[0]):
            # verify correct response was given
            self.error("Expected %r, got %r.  Ignoring" % (resp, msg[0]))
            return None
        self.heavydebug("Received %r" % (msg,))
        return msg

    # TODO: see if we could adjust the "originating" file:line, because
    # otherwise they are all reported from main.py:117 etc
    def heavydebug(self, msg):
        lgr.log(4, msg)

    # Since protocol allows for some messaging back, let's duplicate to lgr
    def debug(self, msg):
        lgr.debug(msg)
        self.send("DEBUG", msg)

    def error(self, msg, annex_err="ERROR"):
        lgr.error(msg)
        self.send(annex_err, msg)

    def progress(self, perc):
        perc = int(perc)
        if self._progress != perc:
            self.send("PROGRESS", perc)


    def main(self):
        """Interface to the command line tool"""

        try:
            self._in_the_loop = True
            self._loop()
        except AnnexRemoteQuit:
            pass # no harm
        except KeyboardInterrupt:
            self.stop("Interrupted by user")
        except Exception, e:
            self.stop(str(e))
        finally:
            self._in_the_loop = False


    def stop(self, msg=None):
        lgr.info("Stopping communications of %s%s" %
                 (self, ": %s" % msg if msg else ""))
        raise AnnexRemoteQuit(msg)


    def _loop(self):
        """The main loop
        """

        self.send("VERSION", SUPPORTED_PROTOCOL)

        while True:
            l = self.read(n=-1)

            if l is not None and not l:
                # empty line: exit
                self.stop()
                return

            req, req_load = l[0], l[1:]

            method = getattr(self, "req_%s" % req, None)
            if not method:
                self.error("We have no support for %s request, part of %s response"
                           % (req, l))
                self.send("UNSUPPORTED-REQUEST")
                continue

            try:
                method(*req_load)
            except Exception, e:
                self.error("Problem processing %r with parameters %r: %r"
                           % (req, req_load, e))
                lgr.error("Caught exception detail: %s" % format_exc())


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

    def get_URLS(self, key):
        """Gets URL(s) associated with a Key.

        """
        assert(self.url_prefix.encode() == self.url_prefix)
        # FIXME: there seems to be a bug
        # http://git-annex.branchable.com/bugs/GETURLS_doesn__39__t_return_URLs_if_prefix_is_provided/?updated
        # thus for now requesting without prefix and filtering manually
        #self.send("GETURLS", key, ":" + self.url_prefix)
        # with annex >= 5.20150327+git27-g6af24b6-1, should be alright
        self.send("GETURLS", key, self.url_prefix)
        urls = []
        while True:
            url = self.read("VALUE", 1)[1:]
            if url:
                assert(len(url) == 1)
                urls.append(url[0])
            else:
                break
        urls_ = [u for u in urls
                if u.startswith(self.url_prefix)]
        assert(urls_ == urls)
        self.heavydebug("Received URLS: %s" % urls)
        return urls

    def _get_file_key(self, file):
        """Return KEY for a given file
        """
        # TODO: should actually be implemented by AnnexRepo
        (out, err) = \
            self.runner(['git-annex', 'lookupkey', file], cwd=self.path)
        return out.rstrip(os.linesep)

    def _get_key_path(self, key):
        """Return path to the KEY file
        """
        # TODO: should actually be implemented by AnnexRepo
        #       Command is available in annex >= 20140410
        (out, err) = \
            self.runner(['git-annex', 'contentlocation', key], cwd=self.path)
        # TODO: it would exit with non-0 if key is not present locally.
        # we need to catch and throw our exception
        return opj(self.path, out.rstrip(os.linesep))

    # TODO: test on annex'es generated with those new options e.g.-c annex.tune.objecthash1=true
    #def get_GETCONFIG SETCONFIG  SETCREDS  GETCREDS  GETUUID  GETGITDIR  SETWANTED  GETWANTED
    #SETSTATE GETSTATE SETURLPRESENT  SETURLMISSING
