# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Support for resolving Singularity Hub URLs
"""

import json
from logging import getLogger

from datalad.dochelpers import borrowkwargs
from datalad.downloaders.http import HTTPDownloader
from datalad.support.exceptions import DownloadError
from datalad.utils import auto_repr

lgr = getLogger("datalad.downloaders.shub")


@auto_repr
class SHubDownloader(HTTPDownloader):
    """Resolve shub:// URLs before handing them off to HTTPDownloader.
    """

    api_url = "https://singularity-hub.org/api/container/"

    @borrowkwargs(HTTPDownloader)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _resolve_url(self, url):
        if not url.startswith("shub://"):
            return url

        info_url = self.api_url + url[7:]
        content = self.fetch(info_url)
        try:
            shub_info = json.loads(content)
        except json.decoder.JSONDecodeError as e:
            raise DownloadError(
                "Failed to get information from {}"
                .format(info_url)) from e
        return shub_info["image"]

    @borrowkwargs(HTTPDownloader)
    def access(self, method, url, *args, **kwargs):
        return super().access(method, self._resolve_url(url), *args, **kwargs)
