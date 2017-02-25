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

from os.path import exists, join as opj, realpath, dirname, lexists

from six.moves import range
from six.moves.urllib.parse import urlparse

import logging
lgr = logging.getLogger('datalad.customremotes')
lgr.log(5, "Importing datalad.customremotes.main")

from ..ui import ui
from ..support.protocol import ProtocolInterface
from ..support.cache import DictCache
from ..cmdline.helpers import get_repo_instance


URI_PREFIX = "dl"
SUPPORTED_PROTOCOL = 1

DEFAULT_COST = 100
DEFAULT_AVAILABILITY = "local"

from datalad.ui.progressbars import ProgressBarBase


class AnnexRemoteQuit(Exception):
    pass


class AnnexExchangeProtocol(ProtocolInterface):
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

    def __init__(self, repopath, custom_remote_name=None):
        super(AnnexExchangeProtocol, self).__init__()
        self.repopath = repopath
        self.custom_remote_name = custom_remote_name
        self._file = None
        self._initiated = False

    def initiate(self):
        if self._initiated:
            return
        self._initiated = True
        d = opj(self.repopath, '.git', 'bin')
        if not exists(d):
            os.makedirs(d)

        suf = '-' + self.custom_remote_name.rstrip(':') if self.custom_remote_name else ''
        self._file = _file = opj(d, 'git-annex-remote-datalad' + suf)

        if exists(_file):
            lgr.debug("Commenting out previous entries")
            # comment out all the past entries
            with open(_file) as f:
                entries = f.readlines()
            for i in range(len(self.HEADER.split(os.linesep)), len(entries)):
                e = entries[i]
                if e.startswith('recv ') or e.startswith('send '):
                    entries[i] = '#' + e
            with open(_file, 'w') as f:
                f.write(''.join(entries))
            return  # nothing else to be done

        lgr.debug("Initiating protocoling."
                  "cd %s; vim %s"
                  % (realpath(self.repopath),
                     _file[len(self.repopath) + 1:]))
        with open(_file, 'a') as f:
            f.write(self.HEADER)
        os.chmod(_file, 0o755)

    def write_section(self, cmd):
        self.initiate()
        with open(self._file, 'a') as f:
            f.write('%s### %s%s' % (os.linesep, cmd, os.linesep))
        lgr.debug("New section in the protocol: "
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

    def start_section(self, cmd):
        self._sections.append({'command': cmd})
        self.write_section(cmd)
        return len(self._sections) - 1

    def end_section(self, id_, exception):
        # raise exception in case of invalid id_ for consistency:
        self._sections.__getitem__(id_)

    def add_section(self, cmd, exception):
        self.start_section(cmd)

    @property
    def records_callables(self):
        return False

    @property
    def records_ext_commands(self):
        return True

    @property
    def do_execute_ext_commands(self):
        return True

    @property
    def do_execute_callables(self):
        return True


class AnnexCustomRemote(object):
    """Base class to provide custom special remotes for git-annex

    Implements git-annex special custom remotes protocol described
    at
    http://git-annex.branchable.com/design/external_special_remote_protocol/
    """

    # Must be defined in subclasses.  There is no classlevel properties, so leaving as this for now

    CUSTOM_REMOTE_NAME = None  # if None -- no additional custom remote name
    # SUPPORTED_SCHEMES = ()

    COST = DEFAULT_COST
    AVAILABILITY = DEFAULT_AVAILABILITY

    def __init__(self, path=None, cost=None):  # , availability=DEFAULT_AVAILABILITY):
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
        from ..support.annexrepo import AnnexRepo
        from ..cmd import GitRunner

        self.runner = GitRunner()

        # Custom remotes correspond to annex via stdin/stdout
        self.fin = sys.stdin
        self.fout = sys.stdout

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

        # To signal either we are in the loop and e.g. could correspond to annex
        self._in_the_loop = False
        self._protocol = \
            AnnexExchangeProtocol(self.path, self.CUSTOM_REMOTE_NAME) \
            if os.environ.get('DATALAD_TESTS_PROTOCOLREMOTE') else None

        self._contentlocations = DictCache(size_limit=100)  # TODO: config ?

        # instruct annex backend UI to use this remote
        if ui.backend == 'annex':
            ui.set_specialremote(self)

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
        if not self._in_the_loop:
            lgr.debug("We are not yet in the loop, thus should not send to annex"
                      " anything.  Got: %s" % msg.encode())
            return
        try:
            self.heavydebug("Sending %r" % msg)
            self.fout.write(msg + "\n")  # .encode())
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
            self.error("Expected %r, got %r.  Ignoring" % (req, msg[0]))
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
            except Exception as e:
                self.error("Problem processing %r with parameters %r: %r"
                           % (req, req_load, e))
                from traceback import format_exc
                lgr.error("Caught exception detail: %s" % format_exc())

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

    # TODO: we should unify what to be overriden and some will provide CHECKURL

    def req_TRANSFER(self, cmd, key, file):
        if cmd in ("RETRIEVE",):
            lgr.debug("%s key %s into/from %s" % (cmd, key, file))  # was INFO level
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

    def get_URLS(self, key):
        """Gets URL(s) associated with a Key.

        """
        urls = []
        for scheme in self.SUPPORTED_SCHEMES:
            scheme_ = scheme + ":"
            self.send("GETURLS", key, scheme_)
            while True:
                url = self.read("VALUE", 1)
                if not url or len(url) <= 1:
                    # so there were no URL output, we must be done
                    break
                url = url[1:]
                if url:
                    assert(len(url) == 1)
                    urls.append(url[0])
                else:
                    break

        self.heavydebug("Got %d URL(s) for key %s: %s", len(urls), key, urls)

        #if not urls:
        #    raise ValueError("Did not get any URLs for %s which we support" % key)

        return urls

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


def generate_uuids():
    """Generate UUIDs for our remotes. Even though quick, for consistency pre-generated and recorded in consts.py"""
    import uuid
    return {
        remote: str(uuid.uuid5(uuid.NAMESPACE_URL, 'http://datalad.org/specialremotes/%s' % remote))
        for remote in {'datalad', 'datalad-archives'}
    }


def init_datalad_remote(repo, remote, encryption=None, autoenable=False, opts=[]):
    """Initialize datalad special remote"""
    from datalad.support.external_versions import external_versions
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
    lgr.info("Initiating special remote %s" % remote)
    remote_opts = [
        'encryption=%s' % str(encryption).lower(),
        'type=external',
        'autoenable=%s' % str(bool(autoenable)).lower(),
        'externaltype=%s' % remote
    ]
    if external_versions['cmd:annex'] >= '6.20170208':
        # use unique uuid for our remotes
        # This should help with merges of disconnected repos etc
        # ATM only datalad/datalad-archives is expected,
        # so on purpose getitem
        remote_opts.append('uuid=%s' % DATALAD_SPECIAL_REMOTES_UUIDS[remote])
    return repo.init_remote(remote, remote_opts + opts)


lgr.log(5, "Done importing datalad.customremotes.main")
