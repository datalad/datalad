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

import os
from os.path import join as opj, exists, relpath
from datalad.interface.base import Interface
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import if_dirty_opt
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    Dataset, require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..log import lgr
from . import get_metadata, get_native_metadata, metadata_filename, \
    metadata_basepath, is_implicit_metadata
from datalad.support.json_py import dump as jsondump


def _store_json(path, meta):
    if not exists(path):
        os.makedirs(path)
    fname = opj(path, metadata_filename)
    jsondump(meta, fname)


class AggregateMetaData(Interface):
    """Aggregate meta data of a dataset for later query.
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
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    def __call__(dataset, guess_native_type=False, recursive=False,
                 recursion_limit=None, if_dirty='save-before'):
        dataset = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        # make sure we get to an expected state
        handle_dirty_dataset(dataset, if_dirty)

        # track whether we modified anything during aggregation, so it becomes
        # possible to decide what to save one level up
        _modified_flag = False

        if dataset.id is None:
            lgr.warning('%s has not configured ID, skipping.', dataset)
            return _modified_flag

        # use one set of subdataset instances to ensure consistent IDs even
        # when none is configured
        # we only want immediate subdatasets, higher depths will come via
        # recursion
        subdss = [Dataset(opj(dataset.path, subds_path))
                  for subds_path in dataset.get_subdatasets(
                      recursive=False)]
        # anything below only works for installed subdatasets
        subdss = [d for d in subdss if d.is_installed()]

        # recursive, depth first
        if recursive and (recursion_limit is None or recursion_limit):
            for subds in subdss:
                subds_modified = AggregateMetaData.__call__(
                    subds,
                    guess_native_type=guess_native_type,
                    recursive=recursive,
                    recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                    if_dirty=if_dirty
                )
                if subds_modified:
                    # stage potential changes in this submodule
                    dataset.repo.add(relpath(subds.path, dataset.path),
                                     git=True)
                    _modified_flag = True

        lgr.info('aggregating meta data for {}'.format(dataset))
        # root path
        metapath = opj(dataset.path, metadata_basepath)

        # this dataset's meta data
        # actually ask to extract native meta data, because we know we have this
        # dataset installed (although maybe not all native metadata)
        # Important: do not store implicit metadata, as this will be largely
        # invalid in a new clone, and is relatively inexpensive to produce
        # from material that is guaranteed to be present after a plain clone
        native_metadata = get_native_metadata(
            dataset,
            guess_type=guess_native_type)
        if native_metadata:
            # avoid practically empty files
            _store_json(metapath, native_metadata)
            _modified_flag = True

        for subds in subdss:
            subds_relpath = relpath(subds.path, dataset.path)
            subds_meta = get_metadata(
                subds, guess_type=guess_native_type, ignore_subdatasets=False,
                ignore_cache=False)
            # find implicit meta data for all contained subdatasets
            for m in subds_meta:
                # skip non-implicit
                if not is_implicit_metadata(m):
                    continue
                if m.get('@id', None) == subds.id:
                    # register relation to dataset being aggregated into
                    m['dcterms:isPartOf'] = dataset.id
            _store_json(
                opj(metapath, subds_relpath),
                subds_meta)
            _modified_flag = True

        # double check might be redundant now, but it is also rather cheap
        if _modified_flag and exists(opj(dataset.repo.path, metapath)):
            dataset.repo.add(metapath, git=True)
            if dataset.repo.repo.is_dirty(
                    index=True,
                    working_tree=False,
                    submodules=True):
                dataset.save(message="[DATALAD] aggregated meta data")

        # report modifications, e.g. to the superdataset aggregate call
        return _modified_flag
