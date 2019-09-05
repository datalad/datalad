# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Management of cookies for HTTP sessions"""

import atexit
import shelve
import pickle
import appdirs
import os.path

from .network import get_tld
from datalad.dochelpers import exc_str

import logging
lgr = logging.getLogger('datalad.cookies')


# FIXME should make into a decorator so that it closes the cookie_db upon exiting whatever func uses it
class CookiesDB(object):
    """Some little helper to deal with cookies

    Lazy loading from the shelved dictionary

    TODO: this is not multiprocess or multi-thread safe implementation due to shelve auto saving etc
    """
    def __init__(self, filename=None):
        self._filename = filename
        self._cookies_db = None
        atexit.register(self.close)

    @property
    def cookies_db(self):
        if self._cookies_db is None:
            self._load()
        return self._cookies_db

    def _load(self):
        if self._cookies_db is not None:
            return
        if self._filename:
            filename = self._filename
            cookies_dir = os.path.dirname(filename)
        else:
            cookies_dir = os.path.join(appdirs.user_config_dir(), 'datalad')  # FIXME prolly shouldn't hardcode 'datalad'
            filename = os.path.join(cookies_dir, 'cookies')

        # TODO: guarantee restricted permissions

        if not os.path.exists(cookies_dir):
            os.makedirs(cookies_dir)

        lgr.debug("Opening cookies DB %s", filename)
        try:
            self._cookies_db = shelve.open(filename, writeback=True, protocol=2)
        except Exception as exc:
            lgr.warning("Failed to open cookies DB %s: %s", filename, exc_str(exc))

    def close(self):
        if self._cookies_db is not None:
            try:
                # It might print out traceback right on the terminal instead of
                # just throwing an exception
                known_cookies = list(self._cookies_db)
            except:
                # May be already not accessible
                known_cookies = None
            try:
                self._cookies_db.close()
            except Exception as exc:
                if known_cookies:
                    lgr.warning(
                        "Failed to save possibly updated %d cookies (%s): %s",
                        len(known_cookies), ', '.join(known_cookies),
                        exc_str(exc))
            # no cookies - no worries!
            self._cookies_db = None

    def _get_provider(self, url):
        tld = get_tld(url)
        return tld

    def __getitem__(self, url):
        try:
            return self.cookies_db[self._get_provider(url)]
        except Exception as exc:
            lgr.warning("Failed to get a cookie for %s: %s",
                        url, exc_str(exc))
            return None

    def __setitem__(self, url, value):
        try:
            self.cookies_db[self._get_provider(url)] = value
        except Exception as exc:
            lgr.warning("Failed to set a cookie for %s: %s",
                        url, exc_str(exc))

    def __contains__(self, url):
        try:
            return self._get_provider(url) in self.cookies_db
        except Exception as exc:
            lgr.warning("Failed to check for having a cookie for %s: %s",
                        url, exc_str(exc))
            return None


# TODO -- convert into singleton pattern for CookiesDB
cookies_db = CookiesDB()
