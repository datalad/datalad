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
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import allow_dirty
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    Dataset, require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..log import lgr
from . import get_metadata, get_native_metadata, metadata_filename, \
    metadata_basepath
from datalad.support.json_py import dump as jsondump
from datalad.support.dsconfig import ConfigManager
from six import string_types


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
        allow_dirty=allow_dirty,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    def __call__(dataset, guess_native_type=False, save=False, recursive=False,
                 recursion_limit=None, allow_dirty=False):
        dataset = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        # it is important to check this prior diving into subdatasets
        # because we might also modify them
        if save and \
            not allow_dirty and \
                dataset.repo.repo.is_dirty(
                    index=True,
                    working_tree=False,
                    submodules=True):
            raise RuntimeError(
                "not aggregating meta data in {}, saving requested, but unsaved changes are already present".format(
                    dataset))

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
                AggregateMetaData.__call__(
                    subds,
                    guess_native_type=guess_native_type,
                    save=save,
                    recursive=recursive,
                    recursion_limit=None if recursion_limit is None else recursion_limit - 1,
                    allow_dirty=allow_dirty
                )
                # stage potential changes in this submodule
                dataset.repo.add(relpath(subds.path, dataset.path),
                                 git=True)

        # check for OLD datasets without a configured ID, and save the current
        # one it
        dsonly_cfg = ConfigManager(dataset, dataset_only=True)
        if not 'datalad.dataset.id' in dsonly_cfg:
            dsonly_cfg.add(
                'datalad.dataset.id',
                dataset.id,
                where='dataset',
                reload=False)
            dataset.repo.add(opj('.datalad', 'config'), git=True)
            # TODO postpone actual save till unification of save behavior
            # across all commands

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

        for subds in subdss:
            subds_relpath = relpath(subds.path, dataset.path)
            subds_meta = get_metadata(
                subds, guess_type=guess_native_type, ignore_subdatasets=False,
                ignore_cache=False)
            # find implicit meta data for all contained subdatasets
            for m in subds_meta:
                # skip non-implicit
                std_spec = m.get('dcterms:conformsTo', '')
                if not (isinstance(std_spec, string_types)
                        and std_spec.startswith('http://docs.datalad.org/metadata.html#v')):
                    continue
                if m.get('@id', None) == subds.id:
                    # register relation to dataset being aggregated into
                    m['dcterms:isPartOf'] = dataset.id
                # prefix all subdataset location information with the relpath of this
                # subdataset
                if 'dcterms:hasPart' in m:
                    parts = m['dcterms:hasPart']
                    if not isinstance(parts, list):
                        parts = [parts]
                        for p in parts:
                            if not 'location' in p:
                                continue
                            loc = p.get('location', subds_relpath)
                            if loc != subds_relpath:
                                p['location'] = opj(subds_relpath, loc)
            _store_json(
                opj(metapath, subds_relpath),
                subds_meta)
        if save and exists(opj(dataset.repo.path, metapath)):
            dataset.repo.add(metapath, git=True)
            if dataset.repo.repo.is_dirty(
                    index=True,
                    working_tree=False,
                    submodules=True):
                dataset.save(message="[DATALAD] save aggregated meta data")
