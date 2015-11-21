# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Sub-module to provide access (as to download/query etc) to the remote sites

"""

__docformat__ = 'restructuredtext'

from six.moves.urllib.parse import urlparse


from .http import HTTPDownloader
from .providers import ProvidersInformation

from logging import getLogger
lgr = getLogger('datalad.providers')

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

lgr.debug("Initializing data providers credentials interface")
providers_info = ProvidersInformation()