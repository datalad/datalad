# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for managing metadata
"""

__docformat__ = 'restructuredtext'


import json
import codecs
import os
from os.path import join as opj, exists
from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    Dataset, require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..log import lgr
from . import get_metadata, extract_metadata, metadata_filename, metadata_basepath, \
    json_dump_kwargs, flatten_metadata_graph


def _optimize_jsonld(obj):
    try:
        from pyld import jsonld
    except ImportError:
        lgr.debug('pyld not available, not compacting meta data graph')
        return obj
    return flatten_metadata_graph(obj)


def _store_json(path, meta, optimize=True):

    if not exists(path):
        os.makedirs(path)

    fname = opj(path, metadata_filename)

    if optimize:
        meta = _optimize_jsonld(meta)

    json.dump(
        meta,
        codecs.getwriter('utf-8')(open(fname, 'wb+')),
        **json_dump_kwargs)


class AggregateMetaData(Interface):
    """Aggregate meta data of a (super)dataset for later query.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        guess_native_type=Parameter(
            args=("--guess-native-type",),
            action="store_true",
            doc="""guess native meta data type of datasets, if none is
            configured. With a configured, or auto-detected meta data type,
            no native meta data will be aggregated."""),
        optimize_metadata=Parameter(
            args=("--optimize-metadata",),
            action="store_true",
            doc="""perform optimization (compacting/flattening) of the meta data
            graph. This functionality requires network access for meta data term
            resolution."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    def __call__(dataset, guess_native_type=False, optimize_metadata=False,
                 recursive=False, recursion_limit=None):
        dataset = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        if recursive:
            # recursive, depth first
            if recursion_limit is None or recursion_limit:
                for subds_path in dataset.get_subdatasets(recursive=False):
                    subds = Dataset(opj(dataset.path, subds_path))
                    if subds.is_installed():
                        AggregateMetaData.__call__(
                            Dataset(opj(dataset.path, subds_path)),
                            guess_native_type=guess_native_type,
                            recursive=recursive,
                            recursion_limit=None if recursion_limit is None
                            else recursion_limit - 1)

        lgr.info('aggregating meta data for {}'.format(dataset))

        # root path
        metapath = opj(dataset.path, metadata_basepath)

        # this dataset's meta data
        _store_json(
            metapath,
            # actually extract meta data, because we know we have this
            # dataset installed (although maube not all native metadata)
            extract_metadata(dataset, guess_type=guess_native_type),
            optimize=optimize_metadata)

        # we only want immediate subdatasets, high depths will come via
        # recursion
        for subds_path in dataset.get_subdatasets(recursive=False):
            subds = Dataset(opj(dataset.path, subds_path))
            if not subds.is_installed():
                lgr.info('ignoring subdataset {}, not installed'.format(subds))
                continue
            _store_json(
                opj(metapath, subds_path),
                # do not extract_metadata here, but `get` to yield one
                # compact metadata set for each subdataset, possibly even
                # for not-installed subdatasets one level down, by using
                # their cached metadata
                get_metadata(subds),
                optimize=optimize_metadata)
