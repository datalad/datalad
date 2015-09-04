# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to stuff (html, data files) via HTTP and HTTPS

"""

__docformat__ = 'restructuredtext'

import re

from six.moves import iteritems
from six.moves.urllib.parse import urlparse

class DownloadError(Exception):
    pass


class Downloaders(object):
    def __init__(self):
        self._downloaders = {}

    def get_downloader(self, url):
        """Generate a new downloader per each website
        """
        url_split = urlparse(url)
        key = (url_split.scheme, url_split.netloc)
        if key in self._downloaders:
            return self._downloaders[key]
        downloader = self._downloaders[key] = HTTPDownloader()
        return downloader


class HTTPDownloader(object):
    """A stateful downloader to maintain a session to the website
    """

    def __init__(self, request_deposition_filename=True):
        pass

    def get(self, url, path=None):
        """
        Parameters
        ----------
        url : string
          URL to access
        path : str, optional
          Either full path to the file, or if exists and a directory
          -- the directory to save under. If just a filename -- store
          under curdir. If None -- fetch and return.
        """
        # TODO: possibly wrap this logic outside within a decorator, which
        # would just call the corresponding method (logic "DOWNLOAD SHIT" here)

        if creds.needs_authentication(url):
            self._authenticate(url, allow_old_cookie=True)
        # DOWNLOAD SHIT
        # if 403 (Access denied) -- we do now that it needs authentication
        # but if not sites.needs_authentication(url) -- we didn't know that
        # we had to authenticate
        if 403:
            creds.get_credentials(url)

        success = True
        if not success:
            self._authenticate(url, allow_old_cookie=False)
            # TRY TO DOWNLOAD SHIT AGAIN
            if not success:
                lgr.debug("Bail")
                raise DownloadError("URL %s failed to download" % url)
        # borrow functionality from __download
        raise NotImplementedError()

    def check(self, url):
        """
        Parameters
        ----------
        url : string
          URL to access
        """
        raise NotImplementedError()


def resolve_url_to_name(d, url):
    """Given a directionary (e.g. of SiteInformation._items or Credential._items)
    go through url_re and find the corresponding item and returns its key (i.e. name)
    """

    for k, rec in iteritems(d):
        for url_re in rec.get('url_re', '').split('\n'):
            if url_re:
                if re.search(url_re, url):
                    return k
    return None


class SitesInformation(object):
    def load(self):
        """Would load information about related/possible websites requiring authentication from

        - current handle .datalad/sites/
        - user dir  ~/.config/datalad/sites/
        - system-wide datalad installation/config /etc/datalad/sites/

        Just load all the files, for now in the form of

        [downloader:crcns]
        url_re = https?://crcns.org/.*
                 https?://portal.nersc.gov/.*
        certificates = ??? (uses https)
        credentials_url = https://crcns.org/request-account/

        """
    pass

    def __contains__(self, url):
        # go through the known ones, and if found a match -- return True, if not False
        raise NotImplementedError

    def get(self, url, field=None):
        # if no field == return all values as a dict
        raise NotImplementedError


class Credentials(object):
    """The store of login:password information

        - current handle .datalad/creds/
        - user dir  ~/.config/datalad/creds/
        - system-wide datalad installation/config /etc/datalad/creds/

        Just load all the files, for now in the form of

        [credentials:crcns]
        url_re = .... # optional
        user = ...
        password = ...

    """

    def __init__(self):
        self.sites = SitesInformation()
        self._items = {}
        self._load() # populate items with information from the those files

    def _load(self):
        raise NotImplementedError()

    def needs_credentials(self, url):
        return "TODO: url known to self._items" or url in self.sites

    def get_credentials(self, url):
        # find a match among _items
        name = resolve_url_to_name(self._items, url)
        if name:
            return self._items[name]
        else:
            rec = self._get_new_record_ui(url)
            rec['url_re'] = "TODO" # figure out
            name = urlparse(url).netloc
            self._items[name] = rec
            if ui.yesno("Do you want to store credentials for %s" % name):
                self.store_credentials()
            return rec

    def store_credentials(self, name):
        # TODO: store  self._items[name]  in appropriate (user) creds
        # for later reuse
        raise NotImplementedError()

    def _get_new_record_ui(self, url):
        ui.message("To access %s we would need credentials.")
        if url in self.sites:
            ui.message("To get credentials please visit %s" % self.sites.get(url, 'credentials_url'))
        return { 'user': ui.question("Username:"),
                 'password': ui.password() }


creds = Credentials()
