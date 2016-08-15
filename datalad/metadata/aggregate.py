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
from os.path import join as opj, exists
from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    Dataset, require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..log import lgr
from . import get_metadata, get_native_metadata, metadata_filename, \
    metadata_basepath, get_dataset_identifier
from datalad.support.json import dump as jsondump


def _store_json(path, meta):
    if not exists(path):
        os.makedirs(path)
    fname = opj(path, metadata_filename)
    jsondump(meta, fname)


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
        save=Parameter(
            args=('--save',),
            action='store_true',
            doc="""save aggregated meta data in the dataset(s). If a dataset has
            unsaved changes, setting this flag will cause an error to avoid
            accidentally saving arbitrary changes."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    def __call__(dataset, guess_native_type=False, save=False, recursive=False,
            recursion_limit=None):
        dataset = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        # it is important to check this prior diving into subdatasets
        # because we might also modify them
        if save and dataset.repo.repo.is_dirty(index=True,
                                               working_tree=False,
                                               submodules=True):
            raise RuntimeError(
                "not aggregating meta data in {}, saving requested, but unsaved changes are already present".format(
                    dataset))

        if recursive:
            # recursive, depth first
            if recursion_limit is None or recursion_limit:
                for subds_path in dataset.get_subdatasets(recursive=False):
                    subds = Dataset(opj(dataset.path, subds_path))
                    if subds.is_installed():
                        AggregateMetaData.__call__(
                            Dataset(opj(dataset.path, subds_path)),
                            guess_native_type=guess_native_type,
                            save=save,
                            recursive=recursive,
                            recursion_limit=None if recursion_limit is None
                            else recursion_limit - 1)
                        # stage potential changes in this submodule
                        dataset.repo.add(subds_path, git=True)

        lgr.info('aggregating meta data for {}'.format(dataset))

        # root path
        metapath = opj(dataset.path, metadata_basepath)

        # this dataset's meta data
        _store_json(
            metapath,
            # actually extract native meta data, because we know we have this
            # dataset installed (although maybe not all native metadata)
            # Important: do not store implicit metadata, as this will be largely
            # invalid in a new clone, and is relatively inexpensive to produce
            # from material that is guaranteed to be present after a plain clone
            get_native_metadata(dataset, guess_type=guess_native_type))

        # we only want immediate subdatasets, higher depths will come via
        # recursion
        for subds_path in dataset.get_subdatasets(recursive=False):
            subds = Dataset(opj(dataset.path, subds_path))
            if not subds.is_installed():
                lgr.info('ignoring subdataset {}, not installed'.format(subds))
                continue
            subds_meta = get_metadata(
                subds, guess_type=guess_native_type, ignore_subdatasets=False,
                ignore_cache=False)
            subds_meta[0]['dcterms:isPartOf'] = get_dataset_identifier(dataset)
            _store_json(opj(metapath, subds_path), subds_meta)
        if save:
            dataset.repo.add(metapath, git=True)
            if dataset.repo.repo.is_dirty(
                    index=True,
                    working_tree=False,
                    submodules=True):
                dataset.save(message="[DATALAD] save aggregated meta data")
