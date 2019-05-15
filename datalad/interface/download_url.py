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

__docformat__ = 'restructuredtext'

import os.path as op

from .base import Interface
from ..interface.base import build_doc
from ..interface.common_opts import nosave_opt
from ..interface.common_opts import save_message_opt
from ..interface.results import get_status_dict
from ..interface.utils import eval_results
from ..utils import assure_list_from_str
from ..utils import get_dataset_pwds
from ..distribution.dataset import datasetmethod
from ..distribution.dataset import EnsureDataset
from ..distribution.dataset import require_dataset
from ..dochelpers import exc_str
from ..support.annexrepo import AnnexRepo, AnnexBatchCommandError
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone
from ..support.exceptions import NoDatasetArgumentFound

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
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to add files to. If no dataset is given,
            an attempt is made to identify the dataset based on the current
            working directory and/or the `path` given. Use [CMD: --nosave
            CMD][PY: save=False PY] to prevent adding files to the dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        overwrite=Parameter(
            args=("-o", "--overwrite"),
            action="store_true",
            doc="""flag to overwrite it if target file exists"""),
        path=Parameter(
            args=("-O", "--path"),
            doc="path (filename or directory path) where to store downloaded file(s).  "
                "In case of multiple URLs provided, must point to a directory.  Otherwise current "
                "directory is used",
            constraints=EnsureStr() | EnsureNone()),
        archive=Parameter(
            args=("--archive",),
            action="store_true",
            doc="""pass the downloaded files to [CMD: :command:`datalad
            add-archive-content --delete` CMD][PY: add_archive_content(...,
            delete=True) PY]"""),
        save=nosave_opt,
        message=save_message_opt
    )

    @staticmethod
    @datasetmethod(name="download_url")
    @eval_results
    def __call__(urls, dataset=None, path=None, overwrite=False,
                 archive=False, save=True, message=None):
        from ..downloaders.providers import Providers

        pwd, rel_pwd = get_dataset_pwds(dataset)

        ds = None
        if save or dataset:
            try:
                ds = require_dataset(
                    dataset, check_installed=True,
                    purpose='downloading urls')
            except NoDatasetArgumentFound:
                pass

        common_report = {"action": "download_url",
                         "ds": ds}

        urls = assure_list_from_str(urls)

        if len(urls) > 1 and path and not op.isdir(path):
            yield get_status_dict(
                status="error",
                message=(
                    "When specifying multiple urls, --path should point to "
                    "an existing directory. Got %r", path),
                type="file",
                path=path,
                **common_report)
            return

        if dataset:  # A dataset was explicitly given.
            path = op.normpath(op.join(ds.path, path or op.curdir))
        elif save and ds:
            path = op.normpath(op.join(ds.path, rel_pwd, path or op.curdir))
        elif not path:
            path = op.curdir

        # TODO setup fancy ui.progressbars doing this in parallel and reporting overall progress
        # in % of urls which were already downloaded
        providers = Providers.from_config_files()
        downloaded_paths = []
        path_urls = {}
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
                path_urls[downloaded_path] = url
                yield get_status_dict(
                    status="ok",
                    type="file",
                    path=downloaded_path,
                    **common_report)

        if downloaded_paths and save and ds is not None:
            msg = message or """\
[DATALAD] Download URLs

URLs:
  {}""".format("\n  ".join(urls))

            for r in ds.save(downloaded_paths, message=msg):
                yield r

            if isinstance(ds.repo, AnnexRepo):
                annex_paths = [p for p, annexed in
                               zip(downloaded_paths,
                                   ds.repo.is_under_annex(downloaded_paths))
                               if annexed]
                if annex_paths:
                    for path in annex_paths:
                        try:
                            # The file is already present. This is just to
                            # register the URL.
                            ds.repo.add_url_to_file(path, path_urls[path],
                                                    batch=True)
                        except AnnexBatchCommandError as exc:
                            lgr.warning("Registering %s with %s failed: %s",
                                        path, path_urls[path], exc_str(exc))

                    if archive:
                        from datalad.api import add_archive_content
                        for path in annex_paths:
                            add_archive_content(path, annex=ds.repo, delete=True)
