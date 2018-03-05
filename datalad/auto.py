# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Proxy basic file operations (e.g. open) to auto-obtain files upon I/O
"""

import sys
# OPT delay import for expensive mock until used
#from mock import patch
from six import PY2
import six.moves.builtins as __builtin__
builtins_name = '__builtin__' if PY2 else 'builtins'

import logging
import io
import os

from os.path import dirname, lexists, realpath, sep as pathsep
from os.path import exists
from os.path import isabs
from os.path import join as opj
from git.exc import InvalidGitRepositoryError

from .utils import getpwd
from .dochelpers import exc_str
from .support.annexrepo import AnnexRepo
from .cmdline.helpers import get_repo_instance
from .consts import HANDLE_META_DIR

# To be used for a quick detection of path being under .git/
_DOT_GIT_DIR = pathsep + '.git' + pathsep

lgr = logging.getLogger("datalad.auto")

h5py = None
try:
    import h5py
except ImportError:
    pass
except Exception as exc:
    # could happen due to misbehaving handlers provided by git module
    # see https://github.com/gitpython-developers/GitPython/issues/600
    # we could overload the handler by providing a blank one, but I do not
    # think it is worthwhile at this point.  So let's just issue a warning
    lgr.warning(
        "Failed to import h5py, so no automagic handling for it atm: %s",
        exc_str(exc)
    )

lzma = None
try:
    import lzma
except ImportError:
    pass
except Exception as exc:
    lgr.warning(
        "Failed to import lzma, so no automagic handling for it atm: %s",
        exc_str(exc)
    )

# TODO: RF to reduce code duplication among cases, also RF tests for the same reason

class _EarlyExit(Exception):
    """Helper to early escape try/except logic in wrapped open"""
    def __init__(self, msg, *args):
        self.msg = msg
        self.args = args


class AutomagicIO(object):
    """Class to proxy commonly used API for accessing files so they get automatically fetched

    Currently supports builtin open() and h5py.File when those are read
    """

    def __init__(self, autoget=True, activate=False, check_once=False):
        """
        
        Parameters
        ----------
        autoget
        activate
        check_once: bool, optional
          To speed things up and avoid unnecessary repeated checks, 
          if True, paths considered for proxying and corresponding repositories
          are remembered, and are not subject to datalad checks on subsequent calls.
          This option is to be used if you do not expect new git repositories to not
          be created and files not to get dropped while operating under 
          AutomagicIO supervision.
        """
        self._active = False
        self._builtin_open = __builtin__.open
        self._io_open = io.open
        self._builtin_exists = os.path.exists
        self._builtin_isfile = os.path.isfile
        if h5py:
            self._h5py_File = h5py.File
        else:
            self._h5py_File = None
        if lzma:
            self._lzma_LZMAFile = lzma.LZMAFile
        else:
            self._lzma_LZMAFile = None
        self._autoget = autoget
        self._in_open = False
        self._log_online = True
        from mock import patch
        self._patch = patch
        self._paths_cache = set() if check_once else None
        self._repos_cache = {} if check_once else None
        if activate:
            self.activate()

    def __enter__(self):
        self.activate()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.deactivate()

    @property
    def autoget(self):
        return self._autoget

    @property
    def active(self):
        return self._active

    def _proxy_open_name_mode(self, origname, origfunc, *args, **kwargs):
        """Proxy for various "open" which have first argument name and 2nd - mode

        """
        # wrap it all for resilience to errors -- proxying must do no harm!
        try:
            if self._in_open:
                raise _EarlyExit("within open already")
            self._in_open = True  # just in case someone kept alias/assignment
            # return stock open for the duration of handling so that
            # logging etc could workout correctly
            with self._patch(origname, origfunc):
                lgr.log(3, "Proxying open with %r %r", args, kwargs)

                # had to go with *args since in PY2 it is name, in PY3 file
                # deduce arguments
                if len(args) > 0:
                    # name/file was provided
                    file = args[0]
                else:
                    filearg = "name" if PY2 else "file"
                    if filearg not in kwargs:
                        # so the name was missing etc, just proxy into original open call and let it puke
                        raise _EarlyExit("no name/file was given")
                    file = kwargs.get(filearg)

                if isinstance(file, int):
                    raise _EarlyExit("already a file descriptor")

                if self._paths_cache is not None:
                    filefull = file if isabs(file) else os.path.abspath(file)
                    if filefull in self._paths_cache:
                        raise _EarlyExit("considered before")
                    else:
                        self._paths_cache.add(filefull)

                if _DOT_GIT_DIR in file:
                    raise _EarlyExit("we ignore paths under .git/")
                mode = 'r'
                if len(args) > 1:
                    mode = args[1]
                elif 'mode' in kwargs:
                    mode = kwargs['mode']

                if 'r' in mode:
                    self._dataset_auto_get(file)
                else:
                    raise _EarlyExit("mode=%r", mode)
        except _EarlyExit as e:
            lgr.log(2, " skipping since " + e.msg, *e.args,
                    extra={'notraceback': True})
        except Exception as e:
            # If anything goes wrong -- we should complain and proceed
            with self._patch(origname, origfunc):
                lgr.warning("Failed proxying open with %r, %r: %s", args, kwargs, exc_str(e))
        finally:
            self._in_open = False
        # finally give it back to stock open
        return origfunc(*args, **kwargs)

    def _proxy_open(self, *args, **kwargs):
        return self._proxy_open_name_mode(builtins_name + '.open', self._builtin_open,
                                          *args, **kwargs)

    def _proxy_io_open(self, *args, **kwargs):
        return self._proxy_open_name_mode('io.open', self._io_open,
                                          *args, **kwargs)

    def _proxy_h5py_File(self, *args, **kwargs):
        return self._proxy_open_name_mode('h5py.File', self._h5py_File,
                                          *args, **kwargs)

    def _proxy_lzma_LZMAFile(self, *args, **kwargs):
        return self._proxy_open_name_mode('lzma.LZMAFile', self._lzma_LZMAFile,
                                          *args, **kwargs)

    def _proxy_exists(self, path):
        # TODO: decide either it should may be retrieved right away.
        # For now, as long as it is a symlink pointing to under .git/annex
        if exists(path):
            return True
        return lexists(path) and 'annex/objects' in str(realpath(path))

    def _proxy_isfile(self, path):
        return self._proxy_open_name_mode(
            'os.path.isfile', self._builtin_isfile, path
        )

    def _dataset_auto_get(self, filepath):
        """Verify that filepath is under annex, and if so and not present - get it"""

        if not self._autoget:
            return
        # if filepath is not there at all (program just "checked" if it could access it
        if not lexists(filepath):
            lgr.log(2, " skipping %s since it is not there", filepath)
            return
        # deduce directory for filepath
        filedir = dirname(filepath)
        annex = None
        if self._repos_cache is not None:
            filedir_parts = filedir.split(pathsep)
            # ATM we do not expect subdatasets under .datalad, so we could take the top
            # level dataset for that
            try:
                filedir = pathsep.join(
                    filedir_parts[:filedir_parts.index(HANDLE_META_DIR)]
                )
            except ValueError:
                # would happen if no .datalad
                pass
            try:
                annex = self._repos_cache[filedir]
            except KeyError:
                pass

        if annex is None:
            try:
                # TODO: verify logic for create -- we shouldn't 'annexify' non-annexified
                # see https://github.com/datalad/datalad/issues/204
                annex = get_repo_instance(filedir)
                lgr.log(2, "Got the repository %s id:%s containing %s", annex, id(annex), filedir)
            except (RuntimeError, InvalidGitRepositoryError) as e:
                # must be not under annex etc
                return
            if self._repos_cache is not None:
                self._repos_cache[filedir] = annex
        if not isinstance(annex, AnnexRepo):
            # not an annex -- can do nothing
            lgr.log(2, " skipping %s since the repo is not annex", filepath)
            return
        # since Git/AnnexRepo functionality treats relative paths relative to the
        # top of the repository and might be outside, get a full path
        if not isabs(filepath):
            filepath = opj(getpwd(), filepath)

        # "quick" check first if under annex at all
        try:
            # might fail.  TODO: troubleshoot when it does e.g.
            # datalad/tests/test_auto.py:test_proxying_open_testrepobased
            under_annex = annex.is_under_annex(filepath, batch=True)
        except:  # MIH: really? what if MemoryError
            under_annex = None
        # either it has content
        if (under_annex or under_annex is None) and not annex.file_has_content(filepath):
            lgr.info("AutomagicIO: retrieving file content of %s", filepath)
            out = annex.get(filepath)
            if not out.get('success', False):
                # to assure that it is present and without trailing/leading new lines
                out['note'] = out.get('note', '').strip()
                lgr.error("Failed to retrieve %(file)s: %(note)s", out)

    def activate(self):
        # we should stay below info for this message. With PR #1630 we
        # start to use this functionality internally, and this will show
        # up frequently even in cases where it does nothing at all
        lgr.debug("Activating DataLad's AutoMagicIO")
        # Some beasts (e.g. tornado used by IPython) override outputs, and
        # provide fileno which throws exception.  In such cases we should not log online
        self._log_online = hasattr(sys.stdout, 'fileno') and hasattr(sys.stderr, 'fileno')
        try:
            if self._log_online:
                sys.stdout.fileno()
                sys.stderr.fileno()
        except:  # MIH: IOError?
            self._log_online = False
        if self.active:
            # this is not a warning, because there is nothing going
            # wrong or being undesired. Nested invokation could happen
            # caused by independent pieces of code, e.g. user code
            # that invokes our own metadata handling.
            lgr.debug("%s already active. No action taken" % self)
            return
        # overloads
        __builtin__.open = self._proxy_open
        io.open = self._proxy_io_open
        os.path.exists = self._proxy_exists
        os.path.isfile = self._proxy_isfile
        if h5py:
            h5py.File = self._proxy_h5py_File
        if lzma:
            lzma.LZMAFile = self._proxy_lzma_LZMAFile
        self._active = True

    def deactivate(self):
        # just debug level -- see activate()
        lgr.debug("Deactivating DataLad's AutoMagicIO")
        if not self.active:
            lgr.warning("%s is not active, can't deactivate" % self)
            return
        __builtin__.open = self._builtin_open
        io.open = self._io_open
        if h5py:
            h5py.File = self._h5py_File
        if lzma:
            lzma.LZMAFile = self._lzma_LZMAFile
        os.path.exists = self._builtin_exists
        os.path.isfile = self._builtin_isfile
        self._active = False

    def __del__(self):
        try:
            if self._active:
                self.deactivate()
        except:  # MIH: IOError?
            pass
        try:
            super(self.__class__, self).__del__()
        except:
            pass
