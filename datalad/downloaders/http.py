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



from six.moves.urllib.parse import urlparse

from ..ui import ui
from .providers import providers_info

from logging import getLogger
lgr = getLogger('datalad.http')

class DownloadError(Exception):
    pass

class AccessDeniedError(DownloadError):
    pass

class Downloaders(object):
    """
    We need custom downloaders to provide authentication
    and some times not supported by annex protocols (e.g. dl+archive, xnat)

    Possible downloaders:

    https?:// -- classical HTTP protocol
    ftp?://
    s3://
    dl+xnat://    dl+xnat://serverurl:port/dataset/path/within
    dl+archive: -- archives (TODO: add //)
    """

    _downloaders = {'http': HTTPDownloader,
                    'https': HTTPDownloader,
                    # ... TODO
                    }

    def __call__(self, url, **kwargs):
        """Generate a new downloader per each website (to maintain the session?)
        """
        url_split = urlparse(url)
        key = (url_split.scheme, url_split.netloc)
        #if key in self._downloaders:
        return self._downloaders[key](**kwargs)
        #downloader = self._downloaders[key] = HTTPDownloader()
        #return downloader


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
        # BEGINNING:
        # if returned None for unknown, True if requires, False if not
        needs_authentication = providers_info.needs_authentication(url)
        if needs_authentication:
            used_old_cookies = self._authenticate(url, allow_old_cookie=True)

        # DOWNLOAD_BEGINS
        try:
            # TODO: DOWNLOAD SHIT

            # !!! HTTP specific
            if response.code != 200: # in {403}:
                raise AccessDenied
            # TODO: not hardcoded size, and probably we should check header
            elif response.content_type == 'text/html' and downloaded_size < 100000:
                # TODO: do matching and decide if it was access_denied
                # if we have no record on that website -- assume that it was a normal
                # load since we don't know better
                raise AccessDenied
            access_denied = False
        except AccessDenied:
            access_denied = True
        except DownloadError:
            # TODO Handle some known ones, otherwise just let it go!
            raise

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
                    #  3. bug in out code which would render authentication/cookie handling
                    #     ineffective
                    #     - not sure what to do about it
                    if ui.yesno(
                            title="Authentication to access {url} has failed".format(url=url),
                            text="Do you want to enter other credentials in case they were updated?"):
                        providers_info.get_credentials(url, new=True)
                        # TODO GOTO BEGINNING
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

        raise NotImplementedError()

    def check(self, url):
        """
        Parameters
        ----------
        url : string
          URL to access
        """
        raise NotImplementedError()


