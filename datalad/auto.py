# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Proxy basic file operations (such as open) to obtain files automagically upon I/O
"""

import sys
from mock import patch
from six import PY2
import six.moves.builtins as __builtin__
builtins_name = '__builtin__' if PY2 else 'builtins'

try:
    import h5py
except ImportError:
    h5py = None

import logging

from os.path import dirname, abspath, pardir, join as opj, exists, basename, lexists
from git.exc import InvalidGitRepositoryError

from .dochelpers import exc_str
from .support.annexrepo import AnnexRepo
from .support.gitrepo import GitRepo
from .support.exceptions import CommandError
from .cmd import Runner
from .cmdline.helpers import get_repo_instance

from .utils import swallow_outputs
lgr = logging.getLogger("datalad.auto")


class _EarlyExit(Exception):
    """Helper to early escape try/except logic in wrappde open"""
    pass

class AutomagicIO(object):
    """Class to proxy commonly used API for accessing files so they get automatically fetched

    Currently supports builtin open() and h5py.File when those are read
    """

    def __init__(self, autoget=True, activate=False):
        self._active = False
        self._builtin_open = __builtin__.open
        if h5py:
            self._h5py_File = h5py.File
        else:
            self._h5py_File = None
        self._autoget = autoget
        self._in_open = False
        self._log_online = True
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
                raise _EarlyExit
            self._in_open = True  # just in case someone kept alias/assignment
            # return stock open for the duration of handling so that
            # logging etc could workout correctly
            with patch(origname, origfunc):
                lgr.log(2, "Proxying open with %r %r", args, kwargs)

                # had to go with *args since in PY2 it is name, in PY3 file
                # deduce arguments
                if len(args) > 0:
                    # name/file was provided
                    file = args[0]
                else:
                    filearg = "name" if PY2 else "file"
                    if filearg not in kwargs:
                        # so the name was missing etc, just proxy into original open call and let it puke
                        lgr.debug("No name/file was given, avoiding proxying")
                        raise _EarlyExit
                    file = kwargs.get(filearg)

                mode = 'r'
                if len(args) > 1:
                    mode = args[1]
                elif 'mode' in kwargs:
                    mode = kwargs['mode']

                if 'r' in mode:
                    self._handle_auto_get(file)
                else:
                    lgr.debug("Skipping operation on %s since mode=%r", file, mode)
        except _EarlyExit:
            pass
        except Exception as e:
            # If anything goes wrong -- we should complain and proceed
            with patch(origname, origfunc):
                lgr.warning("Failed proxying open with %r, %r: %s", args, kwargs, exc_str(e))
        finally:
            self._in_open = False
        # finally give it back to stock open
        return origfunc(*args, **kwargs)

    def _proxy_open(self, *args, **kwargs):
        return self._proxy_open_name_mode(builtins_name + '.open', self._builtin_open,
                                          *args, **kwargs)

    def _proxy_h5py_File(self, *args, **kwargs):
        return self._proxy_open_name_mode('h5py.File', self._h5py_File,
                                          *args, **kwargs)

    def _handle_auto_get(self, filepath):
        """Verify that filepath is under annex, and if so and not present - get it"""

        if not self._autoget:
            return
        # if filepath is not there at all (program just "checked" if it could access it
        if not lexists(filepath):
            lgr.log(2, "Not testing/getting file %s since it is not there", filepath)
            return
        # deduce directory for filepath
        filedir = dirname(filepath)
        try:
            # TODO: verify logic for create -- we shouldn't 'annexify' non-annexified
            # see https://github.com/datalad/datalad/issues/204
            annex = get_repo_instance(filedir)
        except (RuntimeError, InvalidGitRepositoryError) as e:
            # must be not under annex etc
            return
        if not isinstance(annex, AnnexRepo):
            # not an annex -- can do nothing
            return

        # "quick" check first if under annex at all
        try:
            # might fail.  TODO: troubleshoot when it does e.g.
            # datalad/tests/test_auto.py:test_proxying_open_testrepobased
            under_annex = annex.is_under_annex(filepath, batch=True)
        except:
            under_annex = None
        # either it has content
        if (under_annex or under_annex is None) and not annex.file_has_content(filepath):
            lgr.info("File %s has no content -- retrieving", filepath)
            annex.annex_get(filepath, log_online=self._log_online)

    def activate(self):
        # Some beasts (e.g. tornado used by IPython) override outputs, and
        # provide fileno which throws exception.  In such cases we should not log online
        self._log_online = hasattr(sys.stdout, 'fileno') and hasattr(sys.stderr, 'fileno')
        try:
            if self._log_online:
                sys.stdout.fileno()
                sys.stderr.fileno()
        except:
            self._log_online = False
        if self.active:
            lgr.warning("%s already active. No action taken" % self)
            return
        # overloads
        __builtin__.open = self._proxy_open
        if h5py:
            h5py.File = self._proxy_h5py_File
        self._active = True

    def deactivate(self):
        if not self.active:
            lgr.warning("%s is not active, can't deactivate" % self)
            return
        __builtin__.open = self._builtin_open
        if h5py:
            h5py.File = self._h5py_File
        self._active = False

    def __del__(self):
        try:
            if self._active:
                self.deactivate()
        except:
            pass
        try:
            super(self.__class__, self).__del__()
        except:
            pass
