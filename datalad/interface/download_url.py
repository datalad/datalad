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
from ..ui import ui
from ..utils import assure_list_from_str
from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone

from logging import getLogger
lgr = getLogger('datalad.api.download-url')


class DownloadURL(Interface):
    """Download a content from a URL using DataLad's downloader

    It allows for a uniform download interface to various supported URL
    schemes, re-using or asking for authentication detail maintained by
    datalad.

    Examples:

      $ datalad download http://example.com/file.dat s3://bucket/file2.dat
    """

    _params_ = dict(
        urls=Parameter(
            doc="URL(s) to be downloaded.",
            constraints=EnsureStr(),  # TODO: EnsureURL
            metavar='url',
            nargs='+'),
        overwrite=Parameter(
            args=("--overwrite", "-o"),
            action="store_true",
            doc="""Flag to overwrite it if target file exists"""),
        stop_on_failure=Parameter(
            args=("--stop-on-failure", "-x"),
            action="store_true",
            doc="""Flag to stop subsequent downloads upon first failure to download"""),
        path=Parameter(
            args=("--path", '-O'),
            doc="Path (filename or directory path) where to store downloaded file(s). "
                "In case of multiple URLs provided, must point to a directory.  Otherwise current "
                "directory is used",
            constraints=EnsureStr() | EnsureNone())
    )

    @staticmethod
    def __call__(urls, path=None, overwrite=False, stop_on_failure=False):
        """
        Returns
        -------
        list of str
          downloaded successfully files
        """

        from ..downloaders import Providers

        urls = assure_list_from_str(urls)

        if len(urls) > 1:
            if path:
                if not(isdir(path)):
                    raise ValueError(
                        "When specifying multiple urls, --path should point to "
                        "an existing directory. Got %r" % path)
        if not path:
            path = curdir

        # TODO setup fancy ui.progressbars doing this in parallel and reporting overall progress
        # in % of urls which were already downloaded
        providers = Providers.from_config_files()
        downloaded_paths, failed_urls = [], []
        for url in urls:
            # somewhat "ugly"
            # providers.get_provider(url).get_downloader(url).download(url, path=path)
            # for now -- via sugaring
            try:
                downloaded_path = providers.download(url, path=path, overwrite=overwrite)
                downloaded_paths.append(downloaded_path)
                # ui.message("%s -> %s" % (url, downloaded_path))
            except Exception as e:
                failed_urls.append(url)
                ui.error(exc_str(e))
                if stop_on_failure:
                    break
        if failed_urls:
            raise RuntimeError("%d url(s) failed to download" % len(failed_urls))
        return downloaded_paths

