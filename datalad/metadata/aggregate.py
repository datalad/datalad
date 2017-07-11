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

from os.path import join as opj
from os.path import dirname
from os.path import relpath
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.save import Save
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import nosave_opt
from datalad.interface.results import get_status_dict
from datalad.distribution.dataset import Dataset
from datalad.metadata.metadata import Metadata
from datalad.metadata.metadata import agginfo_relpath
from datalad.metadata.metadata import _load_json_object
from datalad.distribution.dataset import datasetmethod, EnsureDataset, require_dataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.log import lgr
from datalad.support.json_py import dump as jsondump


def _adj2subbranches(base, adj):
    # given a set of parent-child mapping, compute a mapping of each parent
    # to all its (grand)children of any depth level
    branches = dict(adj)
    # from bottom up
    for ds in sorted(adj, reverse=True):
        subbranch = []
        for sub in branches[ds]:
            subbranch.append(sub)
            subbranch.extend(branches.get(sub, []))
        branches[ds] = subbranch
    return branches


def _get_obj_location(meta_res):
    # TODO support other metadata result then those for datasets
    if not meta_res.get('metadata', None):
        return None
    return opj('objects', '{}-{}'.format(
        meta_res['type'], meta_res['id']))


@build_doc
class AggregateMetaData(Interface):
    """Aggregate meta data of a dataset for later query.

    By default meta data is aggregated across all configured native meta data
    sources. Optionally, the type of available meta data can guessed, if no
    types are configures. Moreover, it is possible to aggregate meta data from
    any subdatasets into the superdataset, in order to facilitate data
    discovery without having to obtain any subdataset.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""topmost dataset metadata will be aggregated into. All dataset
            betwween this dataset and any given path will received updated
            aggregated metadata from all given paths.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to datasets whose subdataset metadata shall be aggregated.
            When a given path is pointing into a dataset, the metadata of the
            containing dataset will be aggregated.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        guess_native_type=Parameter(
            args=("--guess-native-type",),
            action="store_true",
            doc="""guess native meta data type of datasets, if none is
            configured. With a configured, or auto-detected meta data type,
            no native meta data will be aggregated."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        save=nosave_opt,
    )

    @staticmethod
    @datasetmethod(name='aggregate_metadata')
    @eval_results
    def __call__(
            dataset,
            path,
            guess_native_type=False,
            recursive=False,
            recursion_limit=None,
            save=True):
        # am : does nothing
        # am -d . : does nothing
        # am -d . sub: aggregates sub metadata into .
        # am -d . -r : aggregates metadata of any sub into .

        refds_path = Interface.get_refds_path(dataset)

        # it really doesn't work without a dataset
        ds = require_dataset(
            dataset, check_installed=True, purpose='meta data aggregation')

        # life is simple now, we just query for metadata using the
        # exact same paths that we were given, so everything will be
        # nice and consistent

        # metadata by dataset
        meta_db = {}
        for res in Metadata.__call__(
                dataset=refds_path,
                path=path,
                # TODO expose as selector for aggregation
                #reporton=...
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                on_failure='ignore',
                result_renderer=None):
            if not res['action'] == 'metadata' and res['status'] == 'ok':
                # deflect anything that is not a clean result
                yield res
            assert('parentds' in res or res.get('type', None) == 'dataset')
            # please metadata result into DB under the path of the associated dataset
            for_ds = res['path'] if res.get('type', None) == 'dataset' else res['parentds']
            ds_db = meta_db.get(for_ds, [])
            ds_db.append(res)
            meta_db[for_ds] = ds_db

        # TODO make sure to not create an aggregated copy of a datasets own metadata
        # adjencency info of the dataset tree spanning the base to all leave dataset
        # associated with the path arguments
        ds_adj = {}
        discover_dataset_trace_to_targets(ds.path, meta_db.keys(), [], ds_adj)
        subbranches = _adj2subbranches(ds.path, ds_adj)
        to_save = []
        # go over dataset in bottom-up fashion
        for parent in sorted(subbranches, reverse=True):
            children = subbranches[parent]
            parent = Dataset(parent)
            # load existing aggregate info dict
            agginfo_fpath = opj(parent.path, agginfo_relpath)
            agg_base_path = dirname(agginfo_fpath)
            agginfos = _load_json_object(agginfo_fpath)
            # make list of object files we no longer reference
            objs2remove = set()
            # and new ones
            objs2add = set()
            for child in children:
                child_relpath = relpath(child, start=parent.path)
                prev_objs = set([ci['location'] for ci in agginfos.get(child_relpath, [])])
                # build aggregate info file content
                child_info = [{
                    'type': ci['type'],
                    'id': ci['id'],
                    'shasum': ci['shasum'],
                    'origin': 'datalad',
                    'location': _get_obj_location(ci)}
                    for ci in meta_db[child]]
                agginfos[child_relpath] = child_info
                # write obj files
                objs_current = []
                for ci in meta_db[child]:
                    loc = _get_obj_location(ci)
                    if not loc:
                        # no point in empty files
                        continue
                    opath = opj(agg_base_path, loc)
                    # TODO unlock object file
                    jsondump(ci['metadata'], opj(agg_base_path, loc))
                    to_save.append(dict(path=opath, type='file'))
                    objs_current.append(loc)

                # track changes in object files
                objs_current = [ci['location'] for ci in child_info if ci['location']]
                objs2remove = objs2remove.union(prev_objs.difference(objs_current))
                objs2add = objs2add.union(objs_current)
            # secretly remove obsolete object files, not really a result from a
            # user's perspective
            if objs2remove:
                parent.remove(objs2remove, result_renderer=None, return_type=list)
                if not objs2add and not parent.path == ds.path:
                    # this is not the base dataset, make sure to save removal in the
                    # parent -- not needed when objects get added, as removal itself
                    # is already committed
                    to_save(dict(path=parent.path, type='dataset', staged=True))
            if objs2add:
                # they are added standard way, depending on the repo type
                parent.add(
                    [opj(agg_base_path, p) for p in objs2add],
                    save=False, result_renderer=None, return_type=list)
            # write aggregate info file
            jsondump(agginfos, agginfo_fpath)
            parent.add(agginfo_fpath, save=False, to_git=True,
                       result_renderer=None, return_type=list)
            # queue for save, and mark as staged
            to_save.append(
                dict(path=agginfo_fpath, type='file', staged=True))

            # update complete
            yield get_status_dict(
                status='ok',
                action='aggregate_metadata',
                ds=parent,
                logger=lgr)
        #
        # save potential modifications to dataset global metadata
        #
        if not to_save:
            return
        for res in Save.__call__(
                files=to_save,
                dataset=refds_path,
                message='[DATALAD] dataset aggregate metadata update',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
