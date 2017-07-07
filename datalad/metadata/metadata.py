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
from os.path import curdir
from os.path import exists
from os.path import join as opj
from importlib import import_module

from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
# TODO move next one in here when possible after RF
from datalad.metadata import get_metadata_type
from datalad.metadata.definitions import common_key_defs
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureStr
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
import datalad.support.ansi_colors as ac
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.utils import unique
from datalad.utils import assure_list
from datalad.ui import ui
from datalad.dochelpers import exc_str

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

#
# common manipulator functions
#
def _init(db, spec):
    for k, v in spec.items() if spec else []:
        if k not in db:
            db[k] = v


def _purge(db, spec):
    for k in spec:
        if k in db:
            del db[k]


def _reset(db, spec):
    for k, v in spec.items():
        db[k] = v


def _add(db, spec):
    for k, v in spec.items():
        vals = sorted(unique(
            assure_list(db.get(k, [])) + assure_list(v)))
        if len(vals) == 1:
            vals = vals[0]
        db[k] = vals


def _remove(db, spec):
    for k, v in spec.items():
        existing_data = db.get(k, [])
        if isinstance(existing_data, dict):
            db[k] = {dk: existing_data[dk]
                     for dk in set(existing_data).difference(v)}
        else:
            db[k] = list(set(existing_data).difference(v))
        # wipe out if empty
        if not db[k]:
            del db[k]


# TODO generalize to also work with file metadata
def _merge_global_with_native_metadata(db, ds, nativetypes, mode='init'):
    """Parse a dataset to gather its native metadata

    In-place modification of `db`. Merge multiple native types
    in the order in which they were given.

    Parameters
    ----------
    db : dict
    ds : Dataset
    nativetypes : list
    mode : {'init', 'add', 'reset'}
    """
    mergers = dict(
        init=_init,
        add=_add,
        reset=_reset)

    # keep local, who knows what some parsers might pull in
    from . import parsers
    for nativetype in nativetypes:
        try:
            pmod = import_module('.{}'.format(nativetype),
                                 package=parsers.__package__)
        except ImportError as e:
            lgr.warning(
                "Failed to import metadata parser for '%s', "
                "broken dataset configuration (%s)? "
                "This type of native metadata will be ignored: %s",
                nativetype, ds, exc_str(e))
            continue
        try:
            native_meta = pmod.MetadataParser(ds).get_global_metadata()
        except Exception as e:
            lgr.error('Failed to get native metadata ({}): {}'.format(
                nativetype, exc_str(e)))
            continue
        if not native_meta:
            continue
        if not isinstance(native_meta, dict):
            lgr.error(
                "Metadata parser '%s' yielded something other than a dictionary "
                "for dataset %s -- this is likely a bug, please consider "
                "reporting it. "
                "This type of native metadata will be ignored.",
                nativetype, ds)
            continue
        mergers[mode](db, native_meta)


def _prep_manipulation_spec(init, add, remove, reset):
    """Process manipulation args and bring in form needed by git-annex"""
    # bring metadataset setter args in shape first
    untag, remove = _parse_argspec(remove)
    purge, reset = _parse_argspec(reset)
    tag_add, add = _parse_argspec(add)
    tag_init, init = _parse_argspec(init)
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

    for label, arg in (('init', init),
                       ('add', add),
                       ('remove', remove),
                       ('reset', reset),
                       ('purge', purge)):
        lgr.debug("Will '%s' metadata items: %s", label, arg)
    return init, add, remove, reset, purge


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
        show_keys=Parameter(
            args=('--show-keys',),
            action='store_true',
            doc="""if set, a list of known metadata keys (including the
            origin of their definition) is shown. No other action is
            performed, even if other arguments are given."""),
        permit_undefined_keys=Parameter(
            args=('--permit-undefined-keys',),
            action='store_true',
            doc="""if set, adding (to) undefined metadata keys is
            permitted. By default such an attempt will result in an
            error. It is better to use --define-key to provide
            a definition for a metadata key, or to use pre-defined
            keys (see --show-keys)."""),
        apply2global=Parameter(
            args=('-g', '--apply2global'),
            action='store_true',
            doc="""Whether to perform metadata modification
            on the global dataset metadata, or on individual dataset
            components. For example, without this switch setting
            metadata using the root path of a dataset, will set the
            given metadata for all files in a dataset, whereas with
            this flag only the metadata record of the dataset itself
            will be altered."""),
        reporton=Parameter(
            args=('--report',),
            metavar='TYPE',
            doc="""choose on what type metadata will be reported for
            the requested paths: dataset-global metadata ('datasets'),
            file-based metadata ('files'), any available metadata
            ('all'), or no metadata ('none'; useful when metadata
            is modified, but the resulting state does not need to be
            reported).""",
            constraints=EnsureChoice('all', 'datasets', 'files', 'none')),
        merge_native=Parameter(
            args=('--merge-native',),
            metavar='MODE',
            doc="""merge procedure to use when a dataset provides
            native metadata in some format. Such a dataset has to
            indicate the type of native metadata via its
            configuration setting ``datalad.metadata.nativetype``.
            Multiple different types of metadata are supported. Merging
            is performed in the order in which they are configured.
            Custom DataLad metadata always takes precedence over
            native metadata. Merge procedure modes are semantically
            identical to the corresponding manipulation arguments.
            Setting the mode to 'none' disables merging of native
            metadata.""",
            constraints=EnsureChoice('init', 'add', 'reset', 'none')),

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
            show_keys=False,
            permit_undefined_keys=False,
            apply2global=False,
            reporton='all',
            merge_native='init',
            recursive=False,
            recursion_limit=None):
        # prep args
        init, add, remove, reset, purge = \
            _prep_manipulation_spec(init, add, remove, reset)
        define_key = dict(define_key) if define_key else None

        # prep results
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='metadata', logger=lgr, refds=refds_path)

        if show_keys:
            # to get into the ds meta branches below
            apply2global = True
            for k in sorted(common_key_defs):
                if k.startswith('@'):
                    continue
                ui.message('{}: {} ({})'.format(
                    ac.color_word(k, ac.BOLD),
                    common_key_defs[k],
                    ac.color_word('builtin', ac.MAGENTA)))
            # we need to go on with the command, because further definitions
            # could be provided in each dataset

        if not dataset and not path and not show_keys:
            # makes no sense to have no dataset, go with "here"
            # error generation happens during annotation
            path = curdir

        to_process = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='metadata',
                # TODO later we will be able to report on uninstalled subdatasets via
                # metadata aggregation -> no longer 'error'
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
                    # TODO will no longer be true with aggregated metadata in place
                    continue
                if GitRepo.is_valid_repo(ap['path']):
                    ap['process_content'] = True
            to_process.append(ap)

        # sort paths into datasets
        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        # iterate over all datasets, order doesn't matter
        to_save = []
        for ds_path in content_by_ds:
            # ignore submodule entries
            # TODO with aggregated metadata this will change, we would only ignore
            # when a subdataset is actually installed and we would visit it later
            # otherwise we would reports it aggregated metadata
            content = [ap for ap in content_by_ds[ds_path]
                       if ap.get('type', None) != 'dataset' or ap['path'] == ds_path]
            if not content and not show_keys:
                # nothing other than subdatasets were given or discovered in
                # this dataset, ignore
                continue
            ds = Dataset(ds_path)
            #
            # read dataset metadata, needed in most cases
            # TODO could be made optional, when no global metadata is supposed to be
            # reported, and no key definitions have to be checked
            #
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
            #
            # dedicated key handling
            #
            defs = db.get('definition', {})
            if show_keys:
                for k in sorted(defs):
                    ui.message('{}: {} ({}: {})'.format(
                        ac.color_word(k, ac.BOLD),
                        defs[k],
                        ac.color_word('dataset', ac.MAGENTA),
                        ds.path))
                # no other processing, next dataset
                continue
            #
            # store new key defintions in the dataset
            # we have to do this in every dataset and cannot inherit definitions
            # from a parent, because the metadata in each dataset need to be
            # consistent and self contained, as it may be part of multiple parents
            #
            added_def = False
            if define_key:
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
            #
            # validate keys (only possible once dataset-defined keys are known)
            #
            known_keys = set(common_key_defs.keys()).union(set(defs.keys()))
            key_error = False
            for cat in (init, add, reset) if not permit_undefined_keys else []:
                for k in cat if cat else []:
                    if k not in known_keys:
                        yield get_status_dict(
                            status='error',
                            ds=ds,
                            message=(
                                "undefined key '%s', check spelling or use --define-key "
                                "and consider suggesting a new pre-configured key "
                                "at https://github.com/datalad/datalad/issues/new",
                                k),
                            **res_kwargs)
                        key_error = True
            if key_error:
                return
            #
            # generic global metadata manipulation
            #
            if apply2global or define_key:
                # TODO make manipulation order identical to what git-annex does
                _init(db, init)
                _purge(db, purge)
                _reset(db, reset)
                _add(db, add)
                _remove(db, remove)

                # store, if there is anything, and we could have touched it
                if db and (added_def or init or add or remove or reset or purge):
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
                    ds.add(db_path, save=False, to_git=True)
                    to_save.append(dict(
                        path=db_path,
                        parentds=ds.path,
                        type='file'))
                elif not db and exists(db_path):
                    # no metadata left, kill file
                    ds.remove(db_path)
                    to_save.append(dict(
                        path=ds.path,
                        type='dataset'))
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
            #
            # file metadata manipulation
            #
            ds_paths = [p['path'] for p in content]
            if not apply2global and (reset or purge or add or init or remove):
                mod_paths = []
                for mp in ds.repo.set_metadata(
                        ds_paths,
                        reset=reset,
                        add=add,
                        init=init,
                        remove=remove,
                        purge=purge,
                        # we always go recursive
                        # XXX is that a good thing? But how to otherwise distinuish
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

            #
            # report on this dataset
            #
            if reporton in ('all', 'datasets'):
                res = get_status_dict(
                    status='ok',
                    ds=ds,
                    metadata=db,
                    **res_kwargs)
                # guessing would be expensive, and if the maintainer
                # didn't advertise it we better not brag about it either
                nativetypes = get_metadata_type(ds, guess=False)
                if nativetypes and merge_native != 'none':
                    res['metadata_nativetype'] = nativetypes
                    _merge_global_with_native_metadata(
                        # TODO expose arg, include `None` to disable
                        db, ds, assure_list(nativetypes),
                        mode=merge_native)
                yield res
            #
            # report on this dataset's files
            #
            if reporton in ('all', 'files'):
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

        #
        # save potential modifications to dataset global metadata
        #
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
