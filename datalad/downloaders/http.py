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

from six import iteritems
from six.moves.urllib.parse import urlparse

from ..ui import ui

from logging import getLogger
lgr = getLogger('datalad.http')

class DownloadError(Exception):
    pass


class Downloaders(object):

    def __init__(self):
        self._downloaders = {}

    def get_downloader(self, url):
        """Generate a new downloader per each website (to maintain the session?)
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

        needs_authentication = creds.needs_authentication(url)
        if needs_authentication:
            used_old_cookies = self._authenticate(url, allow_old_cookie=True)
        # DOWNLOAD_BEGINS
        # TODO: DOWNLOAD SHIT

        # !!! HTTP specific
        if response.code in {403}:
            access_denied = True
        # TODO: not hardcoded size, and probably we should check header
        elif response.content-type == 'text/html' and downloaded_size < 100000:
            # TODO: do matching and decide if it was access_denied
            # if we have no record on that website -- assume that it was a normal
            # load since we don't know better
            access_denied = True
        else:
            access_denied = False

        if access_denied:
            if needs_authentication:
                # so we knew it needs authentication
                if used_old_cookies:
                    # Let's try with fresh ones
                    used_old_cookies = self._authenticate(url, allow_old_cookie=False)
                    assert(not used_old_cookies)
                    # TODO GOTO DOWNLOAD_BEGINS
                else:
                    # we did use new cookies, we knew that authentication is needed
                    # but still failed. So possible cases:
                    #  1. authentication credentials changed/were revoked
                    #     - allow user to re-enter credentials
                    #  2. authentication mechanisms changed
                    #     - we can't do anything here about that
                    if ui.yesno(
                            title="Authentication to access {url} has failed",
                            text="Do you want to enter other credentials in case they were updated?"):
                        creds.

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
    """Given a directory (e.g. of SiteInformation._items or Credential._items)
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

        [site:crcns]
        url_re = https?://crcns.org/.*
        certificates = ??? (uses https)
        credentials_url = https://crcns.org/request-account/
        credentials = crcns

        [site:crcns-nersc]
        url_re = https?://portal.nersc.gov/.*
        credentials_url = https://crcns.org/request-account/
        credentials = crcns
        failed_download_re = <form action=".*" method="post">  # so it went to login page
        """
    pass

    def __contains__(self, url):
        # go through the known ones, and if found a match -- return True, if not False
        raise NotImplementedError

    def get(self, url, field=None):
        # if no field == return all values as a dict
        raise NotImplementedError


# TODO: use keyring module for now
class Credentials(object):
    """The interface to the credentials stored by some backend

        - current handle .datalad/creds/
        - user dir  ~/.config/datalad/creds/
        - system-wide datalad installation/config /etc/datalad/creds/

        Just load all the files, for now in the form of

        [credentials:crcns]
        # url_re = .... # optional
        type =    # (user_password|s3_keys(access_key,secret_key for S3)
        # user = ...
        # password = ...

        where actual fields would be stored in a keyring relying on the OS
        provided secure storage

    """

    def __init__(self):
        self.sites = SitesInformation()
        self._items = {}
        self._load()  # populate items with information from the those files

    def _load(self):
        raise NotImplementedError()

    def needs_credentials(self, url):
        return "TODO: url known to self._items" or url in self.sites

    def get_credentials(self, url, new=False):
        # find a match among _items
        name = resolve_url_to_name(self._items, url)
        if new or not name:
            rec = self._get_new_record_ui(url)
            rec['url_re'] = "TODO"  # figure out
            name = urlparse(url).netloc
            self._items[name] = rec
            if ui.yesno("Do you want to store credentials for %s" % name):
                self.store_credentials()
        else:
            return self._items[name]



    def store_credentials(self, name):
        # TODO: store  self._items[name]  in appropriate (user) creds
        # for later reuse
        raise NotImplementedError()

    def _get_new_record_ui(self, url):
        # TODO: should be a dialog with the fields appropriate for this particular
        # type of credentials
        ui.message("To access %s we would need credentials.")
        if url in self.sites:
            self.sites
            ui.message("If you don't yet have credentials, please visit %s"
                       % self.sites.get(url, 'credentials_url'))
        return { 'user': ui.question("Username:"),
                 'password': ui.password() }


creds = Credentials()
