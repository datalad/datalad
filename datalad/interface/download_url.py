# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to DataLad downloaders
"""

# TODO:  or may be it should be converted to 'addurl' thus with option for
# adding into annex or git, depending on the largefiles option, and
# --download-only  to only download... I see myself using it in other projects
# as well I think.

__docformat__ = 'restructuredtext'

from os.path import isdir, curdir

from .base import Interface
from ..interface.base import build_doc
from ..interface.results import get_status_dict
from ..interface.utils import eval_results
from ..utils import assure_list_from_str
from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone

from logging import getLogger
lgr = getLogger('datalad.api.download-url')


@build_doc
class DownloadURL(Interface):
    """Download content

    It allows for a uniform download interface to various supported URL
    schemes, re-using or asking for authentication details maintained by
    datalad.

    Examples:

      $ datalad download-url http://example.com/file.dat s3://bucket/file2.dat
    """

    _params_ = dict(
        urls=Parameter(
            doc="URL(s) to be downloaded",
            constraints=EnsureStr(),  # TODO: EnsureURL
            metavar='url',
            nargs='+'),
        overwrite=Parameter(
            args=("-o", "--overwrite"),
            action="store_true",
            doc="""flag to overwrite it if target file exists"""),
        path=Parameter(
            args=("-O", "--path"),
            doc="path (filename or directory path) where to store downloaded file(s).  "
                "In case of multiple URLs provided, must point to a directory.  Otherwise current "
                "directory is used",
            constraints=EnsureStr() | EnsureNone())
    )

    @eval_results
    @staticmethod
    def __call__(urls, path=None, overwrite=False):
        from ..downloaders.providers import Providers

        common_report = {"action": "download_url"}

        urls = assure_list_from_str(urls)

        if len(urls) > 1 and path and not isdir(path):
            yield get_status_dict(
                status="error",
                message=(
                    "When specifying multiple urls, --path should point to "
                    "an existing directory. Got %r", path),
                type="file",
                path=path,
                **common_report)
            return
        if not path:
            path = curdir

        # TODO setup fancy ui.progressbars doing this in parallel and reporting overall progress
        # in % of urls which were already downloaded
        providers = Providers.from_config_files()
        downloaded_paths = []
        for url in urls:
            # somewhat "ugly"
            # providers.get_provider(url).get_downloader(url).download(url, path=path)
            # for now -- via sugaring
            try:
                downloaded_path = providers.download(url, path=path, overwrite=overwrite)
            except Exception as e:
                yield get_status_dict(
                    status="error",
                    message=exc_str(e),
                    type="file",
                    path=path,
                    **common_report)
            else:
                downloaded_paths.append(downloaded_path)
                yield get_status_dict(
                    status="ok",
                    type="file",
                    path=downloaded_path,
                    **common_report)
