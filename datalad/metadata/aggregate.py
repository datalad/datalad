# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for aggregating metadata
"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj, exists, relpath, dirname
from datalad.interface.base import Interface
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import nosave_opt
from datalad.utils import with_pathsep as _with_sep
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    Dataset, require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from datalad.support.exceptions import CommandError
from ..log import lgr
from . import get_metadata, metadata_filename, metadata_basepath, is_implicit_metadata
from datalad.support.json_py import dump as jsondump


def _store_json(ds, path, meta):
    if not exists(path):
        os.makedirs(path)
    fname = opj(path, metadata_filename)
    jsondump(meta, fname)
    # stage potential changes
    ds.repo.add(fname, git=True)


class AggregateMetaData(Interface):
    """Aggregate meta data of a dataset for later query.

    By default meta data is aggregated across all configured native meta data
    sources. Optionally, the type of available meta data can guessed, if no
    types are configures. Moreover, it is possible to aggregate meta data from
    any subdatasets into the superdataset, in order to facilitate data
    discovery without having to obtain any subdataset.

    Returns
    -------
    List
      Any datasets where (updated) aggregated meta data was saved.
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
        save=nosave_opt,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    def __call__(
            dataset,
            guess_native_type=False,
            recursive=False,
            recursion_limit=None,
            save=True,
            if_dirty='save-before'):
        ds = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')
        modified_ds = []
        if ds.id is None:
            lgr.warning('%s has not configured ID, skipping.', dataset)
            return modified_ds
        # make sure we get to an expected state
        handle_dirty_dataset(ds, if_dirty)

        # if you want to modify the behavior of get_subdataset() make sure
        # there is a way to return the subdatasets DEPTH FIRST!
        ds_meta = {}
        for subds in ds.subdatasets(
                fulfilled=True,
                recursive=recursive,
                recursion_limit=recursion_limit,
                bottomup=True,
                result_xfm='datasets'):
            subds_relpath = relpath(subds.path, start=ds.path)
            if subds.id is None:
                # nothing to worry about, any meta data from below this will be
                # injected upstairs
                lgr.debug('skipping non-dataset at %s', subds.path)
                continue
            else:
                lgr.info('aggregating meta data for %s', subds)
            metapath = opj(subds.path, metadata_basepath)
            handle_dirty_dataset(subds, if_dirty)
            #
            # Phase 1: aggregate the within-dataset meta data, and store
            #          within the dataset
            #
            # pull out meta data from subds only (no subdatasets)
            _within_metadata_store(
                subds,
                guess_native_type,
                metapath)
            #
            # Phase 2: store everything that is in the look up and belongs into
            #          this dataset
            #
            _dump_submeta(subds, ds_meta, subds_relpath, save, modified_ds)
            # save state of modified dataset, all we modified has been staged
            # already
            # we need to save before extracting to full metadata for upstairs
            # consumption to get the versions right
            modified_ds = _save_helper(subds, save, modified_ds)
            #
            # Phase 3: obtain all aggregated meta data from this dataset, and
            #          keep in lookup to escalate it upstairs
            #
            ds_meta[subds_relpath] = get_metadata(
                subds,
                guess_type=False,
                ignore_subdatasets=False,
                ignore_cache=False)

        lgr.info('aggregating meta data for %s', ds)
        # pull out meta data from parent only (no subdatasets)
        _within_metadata_store(
            ds,
            guess_native_type,
            opj(ds.path, metadata_basepath))
        # and lastly the subdatasets of the parent
        _dump_submeta(ds, ds_meta, '', save, modified_ds)
        # everything should be stored somewhere by now
        assert not len(ds_meta)

        # save the parent
        modified_ds = _save_helper(ds, save, modified_ds)


def _within_metadata_store(ds, guess_native_type, metapath):
    meta = get_metadata(
        ds,
        guess_type=guess_native_type,
        ignore_subdatasets=True,
        ignore_cache=True)
    # strip git-based version info from the meta data that is cached
    # in the dataset itself -- this will be outdated the second we
    # commit below
    for m in meta:
        if not is_implicit_metadata(m):
            continue
        for prop in ('dcterms:modified', 'version'):
            if prop in m:
                del m[prop]
    _store_json(ds, metapath, meta)


def _save_helper(ds, save, modified_ds):
    old_state = ds.repo.get_hexsha()
    if save and ds.repo.is_dirty(
            index=True,
            working_tree=False,
            submodules=True):
        ds.save(message="[DATALAD] aggregated meta data")
    if ds.repo.get_hexsha() != old_state:
        modified_ds.append(ds)
    return modified_ds


def _dump_submeta(ds, submetas, matchpath, save, modified_ds):
    known_subds = list(submetas.keys())
    for p in known_subds:
        smeta = submetas[p]
        if matchpath and not p.startswith(_with_sep(matchpath)):
            continue
        subds_relpath = relpath(p, matchpath)
        # inject proper inter-dataset relationships
        for m in smeta:
            # skip non-implicit
            if not is_implicit_metadata(m):
                continue
            if 'dcterms:isPartOf' not in m and m.get('type', None) == 'Dataset':
                m['dcterms:isPartOf'] = ds.id
        sp = opj(ds.path, metadata_basepath, subds_relpath)
        _store_json(ds, sp, smeta)
        # stage potential changes in the subdataset
        try:
            ds.repo.add(subds_relpath, git=True)
        except CommandError:
            # it can blow if we skipped a non-dataset submodule
            # in this case we need to find the chain of submodules leading to it and
            # save then bottom-up
            testpath = dirname(subds_relpath)
            while testpath:
                # TODO this is a slow call that implies pretty bad repeated traversal
                # of dataset trees -- RF to use `subdatasets --contains`
                repo = ds.get_containing_subdataset(testpath)
                repo.repo.add(relpath(subds_relpath, testpath), git=True)
                modified_ds = _save_helper(repo, save, modified_ds)
                # see if there is anything left...
                # IMPORTANT to go with relpath to actually get to an empty
                # string eventually
                testpath = dirname(relpath(repo.path, ds.path))

        # removed stored item from lookup
        del submetas[p]
    return modified_ds
