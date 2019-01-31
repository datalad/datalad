# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run one or more metadata extractors on a dataset or file(s)"""

__docformat__ = 'restructuredtext'

from os import curdir
import os.path as op

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
    EnsureChoice,
)
from datalad.metadata.metadata import (
    _get_metadata,
    _get_metadatarelevant_paths,
    get_metadata_type,
)
from datalad.utils import assure_list

# API commands needed
from datalad.distribution.subdatasets import Subdatasets


@build_doc
class ExtractMetadata(Interface):
    """Run one or more of DataLad's metadata extractors on a dataset or file.

    The result(s) are structured like the metadata DataLad would extract
    during metadata aggregation. There is one result per dataset/file.

    Examples:

      Extract metadata with two extractors from a dataset in the current directory
      and also from all its files::

        $ datalad extract-metadata -d . --source frictionless_datapackage --source datalad_core

      Extract XMP metadata from a single PDF that is not part of any dataset::

        $ datalad extract-metadata --source xmp Downloads/freshfromtheweb.pdf
    """

    _params_ = dict(
        sources=Parameter(
            args=("--source",),
            dest="sources",
            metavar=("NAME"),
            action='append',
            doc="""Name of a metadata extractor to be executed.
            If none is given, a set of default configured extractors,
            plus any extractors enabled in a dataset's configuration
            and invoked.
            [CMD: This option can be given more than once CMD]"""),
        reporton=Parameter(
            args=("--reporton",),
            doc="""dataset component type to report metadata on. If 'all',
            metadata will be reported for the entire dataset and its content.
            If not specified, the dataset's configuration will determine
            the selection, and will default to 'all'.""",
            constraints=EnsureChoice(None, 'all', 'dataset', 'content')),
        path=Parameter(
            args=("path",),
            metavar="FILE",
            nargs="*",
            doc="Path of a file to extract metadata from.",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""Dataset to extract metadata from. If no path is given,
            metadata is extracted from all files of the dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='extract_metadata')
    @eval_results
    def __call__(dataset=None, path=None, sources=None, reporton=None):
        dataset = require_dataset(dataset or curdir,
                                  purpose="extract metadata",
                                  check_installed=not path)

        if not sources:
            sources = ['datalad_core', 'annex'] \
                + assure_list(get_metadata_type(dataset))

        if not path:
            ds = require_dataset(dataset, check_installed=True)
            subds = ds.subdatasets(recursive=False, result_xfm='relpaths')
            paths = list(_get_metadatarelevant_paths(ds, subds))
        else:
            paths = assure_list(path)

        dsmeta, contentmeta, error = _get_metadata(
            dataset,
            sources,
            global_meta=True,
            content_meta=bool(paths),
            paths=paths)

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
                path=op.join(dataset.path, p) if dataset else p,
                refds=dataset.path,
                metadata=contentmeta[p],
                type='file',
                status='error' if error else 'ok')
            if dataset:
                res['parentds'] = dataset.path
            yield res
