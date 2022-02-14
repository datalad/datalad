# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
from logging import getLogger

from datalad.core.local.save import Save
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    path_under_rev_dataset,
    require_dataset,
    resolve_path,
)
from datalad.downloaders.providers import Provider
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    nosave_opt,
    save_message_opt,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    NoDatasetFound,
)
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    PurePosixPath,
    ensure_list_from_str,
)

lgr = getLogger('datalad.local.download-url')


@build_doc
class DownloadURL(Interface):
    """Download content

    It allows for a uniform download interface to various supported URL
    schemes (see command help for details), re-using or asking for
    authentication details maintained by datalad.
    """

    _params_ = dict(
        urls=Parameter(
            doc="""URL(s) to be downloaded. Supported protocols: {}""".format(
                ", ".join(map(repr, sorted(Provider.DOWNLOADERS)))),
            constraints=EnsureStr(),  # TODO: EnsureURL
            metavar='url',
            args=('urls',),
            nargs='+'),
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to add files to. If no dataset is given,
            an attempt is made to identify the dataset based on the current
            working directory. Use [CMD: --nosave CMD][PY: save=False PY] to
            prevent adding files to the dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        overwrite=Parameter(
            args=("-o", "--overwrite"),
            action="store_true",
            doc="""flag to overwrite it if target file exists"""),
        path=Parameter(
            args=("-O", "--path"),
            doc="""target for download. If the path has a trailing separator,
            it is treated as a directory, and each specified URL is downloaded
            under that directory to a base name taken from the URL. Without a
            trailing separator, the value specifies the name of the downloaded
            file (file name extensions inferred from the URL may be added to it,
            if they are not yet present) and only a single URL should be given.
            In both cases, leading directories will be created if needed. This
            argument defaults to the current directory.""",
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

    _examples_ = [
        dict(text="Download files from an http and S3 URL",
             code_py="download_url(urls=['http://example.com/file.dat', 's3://bucket/file2.dat'])",
             code_cmd="datalad download-url http://example.com/file.dat s3://bucket/file2.dat"),
        dict(text="Download a file to a path and provide a commit message",
             code_py="download_url(urls='s3://bucket/file2.dat', message='added a file', path='myfile.dat')",
             code_cmd="""datalad download-url -m 'added a file' -O myfile.dat \\
                         s3://bucket/file2.dat"""),
        dict(text="Append a trailing slash to the target path "
                  "to download into a specified directory",
             code_py="download_url(['http://example.com/file.dat'], path='data/')",
             code_cmd="datalad download-url --path=data/ http://example.com/file.dat"),
        dict(text="Leave off the trailing slash to download into a regular file",
             code_py="download_url(['http://example.com/file.dat'], path='data')",
             code_cmd="datalad download-url --path=data http://example.com/file.dat"),
    ]

    @staticmethod
    @datasetmethod(name="download_url")
    @eval_results
    def __call__(urls,
                 *,
                 dataset=None, path=None, overwrite=False,
                 archive=False, save=True, message=None):
        from ..downloaders.http import HTTPDownloader
        from ..downloaders.providers import Providers

        ds = None
        if save or dataset:
            try:
                ds = require_dataset(
                    dataset, check_installed=True,
                    purpose='download urls')
            except NoDatasetFound:
                pass

        common_report = {"action": "download_url",
                         "ds": ds}

        got_ds_instance = isinstance(dataset, Dataset)
        dir_is_target = not path or str(path).endswith(op.sep)
        path = str(resolve_path(path or op.curdir, ds=dataset))
        if dir_is_target:
            # resolve_path() doesn't preserve trailing separators. Add one for
            # the download() call.
            path = path + op.sep
        urls = ensure_list_from_str(urls)

        if not dir_is_target:
            if len(urls) > 1:
                yield get_status_dict(
                    status="error",
                    message=(
                        "When specifying multiple urls, --path should point to "
                        "a directory target (with a trailing separator). Got %r",
                        path),
                    type="file",
                    path=path,
                    **common_report)
                return
            if archive:
                # make sure the file suffix indicated by a URL is preserved
                # so that any further archive processing doesn't have to
                # employ mime type inspection in order to determine the archive
                # type
                from datalad.support.network import URL
                suffixes = PurePosixPath(URL(urls[0]).path).suffixes
                if not Path(path).suffixes == suffixes:
                    path += ''.join(suffixes)
            # we know that we have a single URL
            # download() would be fine getting an existing directory and
            # downloading the URL underneath it, but let's enforce a trailing
            # slash here for consistency.
            if op.isdir(path):
                yield get_status_dict(
                    status="error",
                    message=(
                        "Non-directory path given (no trailing separator) "
                        "but a directory with that name (after adding archive "
                        "suffix) exists"),
                    type="file",
                    path=path,
                    **common_report)
                return

        # TODO setup fancy ui.progressbars doing this in parallel and reporting overall progress
        # in % of urls which were already downloaded
        providers = Providers.from_config_files()
        downloaded_paths = []
        path_urls = {}
        need_datalad_remote = False
        for url in urls:
            # somewhat "ugly"
            downloader = providers.get_provider(url).get_downloader(url)
            try:
                downloaded_path = downloader.download(url, path=path, overwrite=overwrite)
            except Exception as e:
                ce = CapturedException(e)
                yield get_status_dict(
                    status="error",
                    message=str(ce),
                    type="file",
                    path=path,
                    exception=ce,
                    **common_report)
            else:
                if not need_datalad_remote \
                   and (downloader.authenticator or downloader.credential or
                        type(downloader) != HTTPDownloader):
                    need_datalad_remote = True
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

            for r in Save()(downloaded_paths, message=msg,
                            # ATTN: Pass the original dataset argument to
                            # preserve relative path handling semantics.
                            dataset=dataset,
                            return_type="generator",
                            result_renderer='disabled',
                            result_xfm=None,
                            result_filter=None,
                            on_failure="ignore"):
                yield r

            ds_repo = ds.repo
            if isinstance(ds_repo, AnnexRepo):
                if need_datalad_remote:
                    from datalad.customremotes.base import (
                        ensure_datalad_remote,
                    )
                    ensure_datalad_remote(
                        ds_repo, autoenable=True, encryption=None)

                if got_ds_instance:
                    # Paths in `downloaded_paths` are already relative to the
                    # dataset.
                    rpaths = dict(zip(downloaded_paths, downloaded_paths))
                else:
                    # Paths in `downloaded_paths` are already relative to the
                    # current working directory. Take these relative to the
                    # dataset for use with the AnnexRepo method calls.
                    rpaths = {}
                    for orig_path, resolved in zip(
                            downloaded_paths,
                            resolve_path(downloaded_paths, ds=dataset)):
                        rpath = path_under_rev_dataset(ds, resolved)
                        if rpath:
                            rpaths[str(rpath)] = orig_path
                        else:
                            lgr.warning("Path %s not under dataset %s",
                                        orig_path, ds)
                annex_paths = [p for p, annexed in
                               zip(rpaths,
                                   ds_repo.is_under_annex(list(rpaths.keys())))
                               if annexed]
                if annex_paths:
                    for path in annex_paths:
                        url = path_urls[rpaths[path]]
                        try:
                            # The file is already present. This is just to
                            # register the URL.
                            ds_repo.add_url_to_file(
                                path,
                                url,
                                # avoid batch mode for single files
                                # https://github.com/datalad/datalad/issues/2849
                                batch=len(annex_paths) > 1,
                                # bypass URL size check, we already have the file
                                options=['--relaxed'])
                        except CommandError as exc:
                            lgr.warning("Registering %s with %s failed: %s",
                                        path, url, CapturedException(exc))

                    if archive:
                        for path in annex_paths:
                            yield from ds.add_archive_content(
                                path,
                                delete=True,
                                on_failure='ignore',
                                return_type='generator',
                                result_renderer='disabled'
                            )
