# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Set and query metadata of datasets and their components"""

__docformat__ = 'restructuredtext'


import logging
import re
import json
from os import makedirs
from os.path import dirname
from os.path import relpath
from os.path import exists
from os.path import join as opj

from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.utils import unique

lgr = logging.getLogger('datalad.metadata.metadata')

valid_key = re.compile(r'^[0-9a-z._-]+$')


def _parse_argspec(args):
    """Little helper to get cmdline and python args into a uniform
    shape

    Returns
    -------
    tags, mapping
      A list of tags, and a dict with a mapping of given metadatakeys
      and their associates metadata values
    """
    tags = []
    mapping = {}
    if not args:
        return tags, mapping
    if not isinstance(args, (dict, list, tuple)):
        raise ValueError(
            'invalid metadata specification, must be a dict or sequence')

    asdict = isinstance(args, dict)
    for k in args.items() if isinstance(args, dict) else args:
        v = None
        if asdict:
            # simple, came in from a dict
            k, v = k
            if v:
                mapping[_get_key(k)] = v
            else:
                tags.append(k)
        elif isinstance(k, list):
            # list of lists, came from cmdline
            if len(k) == 1:
                tags.append(k[0])
            elif len(k) > 1:
                mapping[_get_key(k[0])] = k[1:]
            else:
                raise ValueError(
                    'invalid metadata specification, something weird')
        else:
            tags.append(k)
    return tags, mapping


def _get_key(k):
    # annex has caseinsensitive, good enough
    k = k.lower()
    # validate keys against annex constraints
    if not valid_key.match(k):
        raise ValueError(
            'invalid metadata key "{}", must match pattern {}'.format(
                k, valid_key.pattern))
    return k


@build_doc
class Metadata(Interface):
    """Metadata manipulation for files and whole datasets

    Two types of metadata are supported:

    1. metadata describing a dataset as a whole (dataset-global), and

    2. metadata for individual files in a dataset.

    Both types can be accessed and modified with this command.
    Note, however, that this only refers to DataLad's native metadata,
    and not to any other metadata that is possibly stored in files of a
    dataset.

    DataLad's native metadata capability is primarily targeting data
    description via arbitrary tags and other (brief) key-value attributes
    (with possibly multiple values for a single key).

    Metadata key names are limited to alphanumerics (and [_-.]). Moreover,
    all key names are converted to lower case.


    *Dataset (global) metadata*

    Metadata describing a dataset as a whole is stored in JSON format
    in the dataset at .datalad/metadata/dataset.json. The amount of
    metadata that can be stored is not limited by DataLad. However,
    it should be kept brief as this information is stored in the Git
    history of the dataset, and access or modification requires to
    read the entire file.

    Arbitrary metadata keys can be used. However, DataLad reserves the
    keys 'tag' and 'definition' for its own use. The can still be
    manipulated without any restrictions like any other metadata items,
    but doing so can impact DataLad's metadata-related functionality,
    handle with care.

    The 'tag' key is used to store a list of (unique) tags.

    The 'definition' key is used to store key-value mappings that define
    metadata keys used elsewhere in the metadata. Using the feature is
    optional (see --define-key). It can be useful in the context of
    data discovery needs, where metadata keys can be precisely defined
    by linking them to specific ontology terms.


    *File metadata*

    Metadata storage for individual files is provided by git-annex, and
    generally the same rules as for dataset-global metadata apply.
    However, there is just one reserved key name: 'tag'.

    Again, the amount of metadata is not limited, but metadata is stored
    in git-annex' internal data structures in the Git repository of a
    dataset. Large amounts of metadata can slow its performance.


    || CMDLINE >>
    *Output rendering*

    By default, a short summary of the metadata for each dataset
    (component) is rendered::

      <path> (<type>): -|<keys> [<tags>]

    where <path> is the path of the respective component, <type> a label
    for the type of dataset components metadata is presented for. Non-existant
    metadata is indicated by a dash, otherwise a comma-separated list of
    metadata keys (except for 'tag'), is followed by a list of tags, if there
    are any.


    << CMDLINE ||
    """
    # make the custom renderer the default, path reporting isn't the top
    # priority here
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path(s) to set/get metadata",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        add=Parameter(
            args=('-a', '--add',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata items to add. If only a key is given, a
            corresponding tag is added. If a key-value mapping (multiple
            values at once are supported) is given, the values are
            added to the metadata item of that key.""",
            constraints=EnsureStr() | EnsureNone()),
        init=Parameter(
            args=('-i', '--init',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""like --add, but tags are only added if no tag was present
            before. Likewise, values are only added to a metadata key, if that
            key did not exist before.""",
            constraints=EnsureStr() | EnsureNone()),
        remove=Parameter(
            args=('--remove',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata values to remove. If only a key is given, a
            corresponding tag is removed. If a key-value mapping (multiple
            values at once are supported) is given, only those values are
            removed from the metadata item of that key. If no values are left
            after the removal, the entire item of that key is removed.""",
            constraints=EnsureStr() | EnsureNone()),
        reset=Parameter(
            args=('--reset',),
            nargs='+',
            action='append',
            metavar=('KEY', 'VAL'),
            doc="""metadata items to remove. If only a key is given, a
            corresponding metadata key with all its values is removed.
            If a key-value mapping (multiple values at once are supported)
            is given, any existing values for this key are replaced by the
            given ones.""",
            constraints=EnsureStr() | EnsureNone()),
        define_key=Parameter(
            args=('--define-key',),
            nargs=2,
            action='append',
            metavar=('KEY', 'DEFINITION'),
            doc="""convenience option to add an item in the dataset's
            global metadata ('definition' key). This can be used to
            define (custom) keys used in the datasets's metadata, for
            example by providing a URL to an ontology term for a given
            key label. This option does not need --dataset-global to
            be set to be in effect.""",
            constraints=EnsureStr() | EnsureNone()),
        dataset_global=Parameter(
            args=('-g', '--dataset-global'),
            action='store_true',
            doc="""Whether to perform metadata query or modification
            on the global dataset metadata, or on individual dataset
            components. For example, without this switch setting
            metadata using the root path of a dataset, will set the
            given metadata for all files in a dataset, whereas with
            this flag only the metadata record of the dataset itself
            will be altered."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='metadata')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            add=None,
            init=None,
            remove=None,
            reset=None,
            define_key=None,
            dataset_global=False,
            recursive=False,
            recursion_limit=None):
        # bring metadataset setter args in shape first
        untag, remove = _parse_argspec(remove)
        purge, reset = _parse_argspec(reset)
        tag_add, add = _parse_argspec(add)
        tag_init, init = _parse_argspec(init)
        define_key = dict(define_key) if define_key else None
        # merge all potential sources of tag specifications
        all_untag = remove.get('tag', []) + untag
        if all_untag:
            remove['tag'] = all_untag
        all_addtag = add.get('tag', []) + tag_add
        if all_addtag:
            add['tag'] = all_addtag
        all_inittag = init.get('tag', []) + tag_init
        if all_inittag:
            init['tag'] = all_inittag

        lgr.debug("Will 'init' metadata items: %s", init)
        lgr.debug("Will 'add' metadata items: %s", add)
        lgr.debug("Will 'remove' metadata items: %s", remove)
        lgr.debug("Will 'reset' metadata items: %s", reset)
        lgr.debug("Will 'purge' metadata items: %s", purge)

        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='metadata', logger=lgr, refds=refds_path)

        to_process = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='metadata',
                unavailable_path_status='error',
                nondataset_path_status='error',
                force_subds_discovery=False,
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', None) == 'dataset':
                if ap.get('state', None) == 'absent':
                    # just discovered via recursion, but not relevant here
                    continue
                if GitRepo.is_valid_repo(ap['path']):
                    ap['process_content'] = True
            to_process.append(ap)

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path)
        assert(not completed)

        # iterate over all datasets, order doesn't matter
        to_save = []
        for ds_path in content_by_ds:
            # ignore submodule entries
            content = [ap for ap in content_by_ds[ds_path]
                       if ap.get('type', None) != 'dataset' or ap['path'] == ds_path]
            if not content:
                # nothing other than subdatasets were given or discovered in
                # this dataset, ignore
                continue
            ds = Dataset(ds_path)
            if dataset_global or define_key:
                db_path = opj(ds.path, '.datalad', 'metadata', 'dataset.json')
                db = {}
                if exists(db_path):
                    db_fp = open(db_path)
                    # need to read manually, load() would puke on an empty file
                    db_content = db_fp.read()
                    # minimize time for collision
                    db_fp.close()
                    if db_content:
                        db = json.loads(db_content)
                # TODO make manipulation order identical to what git-annex does
                for k, v in init.items() if init else []:
                    if k not in db:
                        db[k] = v
                for k in purge:
                    if k in db:
                        del db[k]
                for k, v in reset.items():
                    db[k] = v
                for k, v in add.items():
                    db[k] = sorted(unique(
                        db.get(k, []) + v))
                for k, v in remove.items():
                    existing_data = db.get(k, [])
                    if isinstance(existing_data, dict):
                        db[k] = {dk: existing_data[dk]
                                 for dk in set(existing_data).difference(v)}
                    else:
                        db[k] = list(set(existing_data).difference(v))
                    # wipe out if empty
                    if not db[k]:
                        del db[k]

                added_def = False
                if define_key:
                    defs = db.get('definition', {})
                    for k, v in define_key.items():
                        if k in defs:
                            if not defs[k] == v:
                                yield get_status_dict(
                                    status='error',
                                    ds=ds,
                                    message=(
                                        "conflicting definition for key '%s': '%s' != '%s'",
                                        k, v, defs[k]),
                                    **res_kwargs)
                                continue
                        else:
                            defs[k] = v
                            added_def = True
                    db['definition'] = defs
                # store, if there is anything
                if db:
                    if not exists(dirname(db_path)):
                        makedirs(dirname(db_path))
                    db_fp = open(db_path, 'w')
                    # produce relatively compact, but also diff-friendly format
                    json.dump(
                        db,
                        db_fp,
                        indent=0,
                        separators=(',', ':\n'),
                        sort_keys=True)
                    # minimize time for collision
                    db_fp.close()
                    # use add not save to also cover case of a fresh file
                    ds.add(db_path, save=False)
                    to_save.append(dict(
                        path=db_path,
                        parentds=ds.path,
                        type='file'))
                elif exists(db_path):
                    # no metadata left, kill file
                    ds.remove(db_path)
                    to_save.append(dict(
                        path=ds.path,
                        type='dataset'))
                if added_def or init or add or remove or reset or purge:
                    # if anything happended or could have happended
                    yield get_status_dict(
                        status='ok',
                        ds=ds,
                        metadata=db,
                        **res_kwargs)
            elif not isinstance(ds.repo, AnnexRepo):
                # report on all explicitly requested paths only
                for ap in [c for c in content if ap.get('raw_input', False)]:
                    yield dict(
                        ap,
                        status='impossible',
                        message=(
                            'non-annex dataset %s has no file metadata support', ds),
                        **res_kwargs)
                continue
            ds_paths = [p['path'] for p in content]
            if not dataset_global:
                if reset or purge or add or init or remove:
                    # file metadata manipulation
                    mod_paths = []
                    for mp in ds.repo.set_metadata(
                            ds_paths,
                            reset=reset,
                            add=add,
                            init=init,
                            remove=remove,
                            purge=purge,
                            # we always go recursive
                            # TODO is that a good thing? But how to otherwise distinuish
                            # this kind of recursive from the one across datasets in
                            # the API?
                            recursive=True):
                        if mp.get('success', False):
                            mod_paths.append(mp['file'])
                        else:
                            yield get_status_dict(
                                status='error',
                                message='setting metadata failed',
                                path=opj(ds.path, mp[0]),
                                type='file',
                                **res_kwargs)
                    # query the actually modified paths only
                    ds_paths = mod_paths

                # and lastly, query -- even if we set before -- there could
                # be side-effect from multiple set paths on an individual
                # path, hence we need to query to get the final result
                for file, meta in ds.repo.get_metadata(ds_paths):
                    r = get_status_dict(
                        status='ok',
                        path=opj(ds.path, file),
                        type='file',
                        metadata=meta,
                        **res_kwargs)
                    yield r
        # save potential modifications to dataset global metadata
        if not to_save:
            return
        for res in Save.__call__(
                path=to_save,
                dataset=refds_path,
                message='[DATALAD] dataset metadata update',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if res['status'] != 'ok' or not res.get('action', None) == 'metadata':
            # logging complained about this already
            return
        # list the path, available metadata keys, and tags
        path = relpath(res['path'],
                       res['refds']) if res.get('refds', None) else res['path']
        meta = res.get('metadata', {})
        ui.message('{path}{type}:{spacer}{meta}{tags}'.format(
            path=path,
            type=' ({})'.format(res['type']) if 'type' in res else '',
            spacer=' ' if len([m for m in meta if m != 'tag']) else '',
            meta=','.join(k for k in sorted(meta.keys()) if not k == 'tag')
                 if meta else ' -',
            tags='' if 'tag' not in meta else ' [{}]'.format(
                 ','.join(meta['tag']))))
