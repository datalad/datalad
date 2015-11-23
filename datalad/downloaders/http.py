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


from ..ui import ui
from ..utils import auto_repr

from .base import BaseDownloader
from .base import DownloadError, AccessDeniedError

from logging import getLogger
lgr = getLogger('datalad.http')

__docformat__ = 'restructuredtext'


@auto_repr
class HTTPDownloader(BaseDownloader):
    """A stateful downloader to maintain a session to the website
    """

    def __init__(self, credential=None, authenticator=None):
        """

        Parameters
        ----------
        TODO
        """
        self.credential = credential
        self.authenticator = authenticator
        if self.authenticator:
            if not self.credential:
                raise ValueError(
                    "Both authenticator and credentials must be provided."
                    " Got only authenticator %s" % repr(authenticator))


    def _authenticate(self, allow_old=True):
        """

        Parameters
        ----------
        allow_old: bool, optional
          If a Downloader allows for persistent sessions by some means -- flag
          instructs either to use previous session, or establish a new one

        Returns
        -------
        bool
          To state if old instance of a session/authentication was used
        """
        pass

    def _access(self, method, url, allow_old_session=True, **kwargs):
        """Fetch content as pointed by the URL optionally into a file

        Parameters
        ----------
        method : callable
          A callable, usually a method of the same class, which we decorate
          with access handling, and pass url as the first argument
        url : string
          URL to access
        *args, **kwargs
          Passed into the method call

        Returns
        -------
        None or bytes
        """
        # TODO: possibly wrap this logic outside within a decorator, which
        # would just call the corresponding method

        authenticator = self.authenticator
        needs_authentication = authenticator and authenticator.requires_authentication

        attempt = 0
        while True:
            attempt += 1
            if attempt > 3:
                # are we stuck in a loop somehow? I think logic doesn't allow this atm
                raise RuntimeError("Got to the %d'th iteration while trying to download %s" % (attempt, url))

            used_old_session = False  # must not matter but just for "robustness"
            if needs_authentication:
                used_old_session = self._authenticate(url, allow_old=allow_old_session)
                if not allow_old_session:
                    assert(not used_old_session)

            access_denied = False
            try:
                result = method(url, **kwargs)
            except AccessDeniedError:
                access_denied = True
            except DownloadError:
                # TODO Handle some known ones, possibly allow for a few retries, otherwise just let it go!
                raise

            if access_denied:  # moved logic outside of except for clarity
                if needs_authentication:
                    # so we knew it needs authentication
                    if used_old_session:
                        # Let's try with fresh ones
                        allow_old_session = False
                        continue
                    else:
                        # we did use new cookies, we knew that authentication is needed
                        # but still failed. So possible cases:
                        #  1. authentication credentials changed/were revoked
                        #     - allow user to re-enter credentials
                        #  2. authentication mechanisms changed
                        #     - we can't do anything here about that
                        #  3. bug in out code which would render authentication/cookie handling
                        #     ineffective
                        #     - not sure what to do about it
                        if ui.yesno(
                                title="Authentication to access {url} has failed".format(url=url),
                                text="Do you want to enter other credentials in case they were updated?"):
                            self.credentials.enter_new()
                            allow_old_session = False
                            continue
                        else:
                            raise DownloadError("Failed to download from %s given available credentials" % url)
                else:  # None or False
                    if needs_authentication is False:
                        # those urls must or should NOT require authentication but we got denied
                        raise DownloadError("Failed to download from %s, which must be available without "
                                            "authentication but access was denied" % url)
                    else:
                        assert(needs_authentication is None)
                        # So we didn't know if authentication necessary, and it seems to be necessary, so
                        # Let's ask the user to setup authentication mechanism for this website
                        raise AccessDeniedError(
                            "Access to %s was denied but we don't know about this data provider. "
                            "You would need to configure data provider authentication using TODO " % url)

        return result


    def _download(self, url, path=None):
        """

        Parameters
        ----------
        url: str
          URL to download
        path: str, optional
          Path to file where to store the downloaded content.  If None, downloaded
          content provided back in the return value (not decoded???)

        Returns
        -------
        None or bytes

        """
        # TODO

        # !!! HTTP specific
        if response.code != 200: # in {403}:
            raise AccessDeniedError
        # TODO: not hardcoded size, and probably we should check header
        elif response.content_type == 'text/html' and downloaded_size < 100000:
            # TODO: do matching and decide if it was access_denied
            # if we have no record on that website -- assume that it was a normal
            # load since we don't know better
            raise AccessDeniedError
        access_denied = False


    def get(self, url, path=None, **kwargs):
        """Fetch content as pointed by the URL optionally into a file

        Parameters
        ----------
        url : string
          URL to access
        path : str, optional
          Either full path to the file, or if exists and a directory
          -- the directory to save under. If just a filename -- store
          under curdir. If None -- fetch and return the fetched content.

        Returns
        -------
        None or bytes
        """
        return self._access(self._download, path=path, **kwargs)


    def _check(self, url):
        raise NotImplementedError("check is not yet implemented")

    def check(self, url):
        """
        Parameters
        ----------
        url : string
          URL to access
        """
        return self._access(self._check, path=path, **kwargs)
