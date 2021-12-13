# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run one or more metadata extractors on a dataset or file(s)"""

__docformat__ = 'restructuredtext'

from os import curdir
from os.path import join as opj

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import require_dataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone, EnsureStr
from datalad.metadata.metadata import _get_metadata
from datalad.metadata.metadata import _get_metadatarelevant_paths


@build_doc
class ExtractMetadata(Interface):
    """Run one or more of DataLad's metadata extractors on a dataset or file.

    The result(s) are structured like the metadata DataLad would extract
    during metadata aggregation. There is one result per dataset/file.

    Examples:

      Extract metadata with two extractors from a dataset in the current directory
      and also from all its files::

        $ datalad extract-metadata -d . --type frictionless_datapackage --type datalad_core

      Extract XMP metadata from a single PDF that is not part of any dataset::

        $ datalad extract-metadata --type xmp Downloads/freshfromtheweb.pdf
    """

    _params_ = dict(
        types=Parameter(
            args=("--type",),
            dest="types",
            metavar=("NAME"),
            action='append',
            required=True,
            doc="""Name of a metadata extractor to be executed.
            [CMD: This option can be given more than once CMD]"""),
        files=Parameter(
            args=("files",),
            metavar="FILE",
            nargs="*",
            doc="Path of a file to extract metadata from.",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""Dataset to extract metadata from. If no `file` is given,
            metadata is extracted from all files of the dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='extract_metadata')
    @eval_results
    # Note: types is a required option and files (path!) is posarg --
    # This is not consistent with the other uses, but since it is being redone in metalad
    # anyways -- kept as is.without adding * following current design docs.
    def __call__(types, files=None, dataset=None):
        dataset = require_dataset(dataset or curdir,
                                  purpose="extract metadata",
                                  check_installed=not files)
        if not files:
            ds = require_dataset(dataset, check_installed=True)
            subds = ds.subdatasets(recursive=False, result_xfm='relpaths')
            files = list(_get_metadatarelevant_paths(ds, subds))

        dsmeta, contentmeta, error = _get_metadata(
            dataset,
            types,
            global_meta=True,
            content_meta=bool(files),
            paths=files)

        if dataset is not None and dataset.is_installed():
            res = get_status_dict(
                action='metadata',
                ds=dataset,
                refds=dataset.path,
                metadata=dsmeta,
                status='error' if error else 'ok')
            yield res

        for p in contentmeta:
            res = get_status_dict(
                action='metadata',
                path=opj(dataset.path, p) if dataset else p,
                refds=dataset.path,
                metadata=contentmeta[p],
                type='file',
                status='error' if error else 'ok')
            if dataset:
                res['parentds'] = dataset.path
            yield res
