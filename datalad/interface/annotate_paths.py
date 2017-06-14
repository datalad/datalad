# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for analyzing and acting upon input paths"""

__docformat__ = 'restructuredtext'


import logging
import textwrap

from os import curdir
from os.path import join as opj
from os.path import lexists
from os.path import isdir
from os.path import dirname
from os.path import pardir
from os.path import normpath
from os.path import sep as dirsep

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import GitRepo
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import get_dataset_root
from datalad.utils import with_pathsep as _with_sep
from datalad.utils import assure_list

lgr = logging.getLogger('datalad.interface.annotate_paths')


def annotated2ds_props(annotated):
    """Return a dict with properties of all datasets in `annotated`.

    Returns
    -------
    dict
    """
    props = {}
    for a in annotated:
        if a.get('type', None) == 'dataset':
            dp = props.get(a['path'], {})
            dp.update(a)
            props[a['path']]
    return props


def annotated2content_by_ds(annotated, refds_path, path_only=False):
    """Helper to convert annotated paths into an old-style content_by_ds dict

    Only items with an `status` property value not equal to 'ok', 'notneeded',
    'impossible', or 'error' are sorted. All others are considered as
    already processed and are returned in a separate list.

    Parameters
    ----------
    annotated : list or generator
      Dicts with annotated path information.
    refds_path : str
      Path to the reference dataset the original path annotation was based on.
    path_only: bool
      Whether returned dict values are sequences of just paths for each
      dataset, or whether the full info dicts are reported as items.

    Returns
    -------
    dict, dict, list, list
      Dict keys are dataset paths, values are determined by the `path_only`
      switch. The keys in the second dict are paths to dataset, values are
      dicts with all known properties about those datasets.
      The first list contains all already "processed" results, which
      typically need to be re-yielded. The second list contains items (same
      type as dict values) for all annotated paths that have no associated
      parent dataset (i.e. nondataset paths) -- this list will be empty by
      default, unless `nondataset_path_status` was set to ''."""
    content_by_ds = {}
    ds_props = {}
    nondataset_paths = []
    completed = []
    for r in annotated:
        if r.get('type', None) == 'dataset':
            # collect all properties of all known datasets from the annotated
            # paths
            dp = ds_props.get(r['path'], {})
            dp.update(r)
            ds_props[r['path']] = dp
        if r.get('status', None) in ('ok', 'notneeded', 'impossible', 'error'):
            completed.append(r)
            continue
        parentds = r.get('parentds', None)
        if r.get('type', None) == 'dataset':
            # to dataset handling first, it is the more complex beast
            orig_request = r.get('orig_request', None)
            if parentds is None or refds_path is None or \
                    r.get('process_content', False) or (orig_request and (
                    orig_request == curdir or
                    orig_request.endswith(dirsep) or
                    orig_request.endswith('{}{}'.format(dirsep, curdir)))):
                # a dataset that floats by on its own OR
                # behave similar to rsync, a trailing '/' indicates the
                # content rather then the dataset itself
                # in both cases we want to process this part as part
                # of the same dataset, and not any potential parent
                toappendto = content_by_ds.get(r['path'], [])
                toappendto.append(r['path'] if path_only else r)
                content_by_ds[r['path']] = toappendto
            if parentds and refds_path and \
                    _with_sep(parentds).startswith(_with_sep(refds_path)):
                # put also in parentds record if there is any, and the parent
                # is underneath or identical to the reference dataset
                toappendto = content_by_ds.get(parentds, [])
                toappendto.append(r['path'] if path_only else r)
                content_by_ds[parentds] = toappendto
        else:
            # files and dirs
            # common case, something with a parentds
            toappendto = content_by_ds.get(parentds, [])
            toappendto.append(r['path'] if path_only else r)
            content_by_ds[parentds] = toappendto

    return content_by_ds, ds_props, completed, nondataset_paths


def yield_recursive(ds, path, action, recursion_limit):
    # make sure we get everything relevant in all _checked out_
    # subdatasets, obtaining of previously unavailable subdataset
    # is elsewhere
    for subd_res in ds.subdatasets(
            recursive=True,
            recursion_limit=recursion_limit,
            return_type='generator'):
        # this check is not the same as subdatasets --contains=path
        # because we want all subdataset below a path, not just the
        # containing one
        if subd_res['path'].startswith(_with_sep(path)):
            # this subdatasets is underneath the search path
            # be careful to not overwrite anything, in case
            # this subdataset has been processed before
            subd_res['action'] = action
            # mark as "notprocessed"
            subd_res['status'] = ''
            # we know that this is a known subdataset, that is how
            # we got here, make a record
            subd_res['registered_subds'] = True
            yield subd_res


def get_modified_subpaths(aps, refds, revision):
    """
    Parameters
    ----------
    aps : list
    refds : Dataset
    revision : str
      Commit-ish
    """
    # TODO needs recursion limit
    # NOTE this is implemented as a generator despite that fact that we need
    # to sort through _all_ the inputs initially, diff'ing each involved
    # dataset takes time that we can use to already act on intermediate
    # result paths, without having to wait for 100% completion
    if revision is None:
        # we want all, subds not matching the ref are assumed to have been
        # sorted out before (e.g. one level up)
        for r in aps:
            yield r

    # life is simple: we diff the base dataset
    modified = []
    for r in refds.diff(
            # we cannot really limit the diff paths easily because we might get
            # or miss content (e.g. subdatasets) if we don't figure out which
            # ones are known -- and we don't want that
            path=None,
            # `revision` can be anything that Git support for `diff`
            # `True` is code for diff without revision
            revision=revision if revision is not True else None,
            staged=False,
            # we might want to consider putting 'untracked' here
            # maybe that is a little faster, not tested yet
            ignore_subdatasets='none',
            # no recursion, we needs to update `revision` for every subdataset
            # before we can `diff`
            recursive=False,
            return_type='generator',
            result_renderer=None):
        if r['status'] in ('impossible', 'error'):
            # something unexpected, tell daddy
            yield r
            continue
        r['status'] = ''
        modified.append(r)

    if not len(modified):
        # nothing modified nothing to report
        return

    # now we can grab the APs that are in this dataset and yield them
    for ap in aps:
        # need to preserve pristine info first
        ap = ap if isinstance(ap, dict) else rawpath2ap(ap, refds.path)
        for m in modified:
            if ap['path'] == m['path']:
                # is directly modified, yield input AP
                # but update with what we learned about the modification
                ap.update(m)
                yield ap
                break
            if m['path'].startswith(_with_sep(ap['path'])):
                # a modified path is underneath this AP
                # yield the modified one instead
                yield m
                continue

    mod_subs = [m for m in modified if m.get('type', None) == 'dataset']
    if not mod_subs:
        return

    aps = [ap if isinstance(ap, dict) else rawpath2ap(ap, refds.path) for ap in aps]
    # now for all submodules that were found modified
    for sub in [m for m in modified if m.get('type', None) == 'dataset']:
        sub_path_ = _with_sep(sub['path'])
        # these AP match something inside this submodule, or the whole submodule
        sub_aps = [ap for ap in aps if _with_sep(ap['path']).startswith(sub_path_)]
        if not sub_aps:
            continue
        # we are interested in the modifications within this subdataset
        # from the state we previously had on record, till the state
        # we have in record now
        diff_range = '{}..{}'.format(
            sub['revision_src'] if sub['revision_src'] else '',
            sub['revision'] if sub['revision'] else '')
        for r in get_modified_subpaths(
                sub_aps,
                Dataset(sub['path']),
                diff_range):
            yield r


def rawpath2ap(path, refds_path):
    orig_path_request = path
    # this is raw, resolve
    path = resolve_path(path, refds_path)
    # collect info on this path
    path_props = dict(
        path=path,
        # path was requested as input, and not somehow discovered
        raw_input=True,
        # make a record of what actually came in, sorting into
        # dataset might later need to distinguish between a path
        # that pointed to a dataset as a whole vs. a path that
        # pointed to the dataset's content -- just do not destroy
        # any information on the way down
        orig_request=orig_path_request)
    return path_props


# "complete" list of recognized properties, there could be other ones
# as any command can inject anything
known_props = {
    'annexkey': 'annex key for the content of a file',
    'action': 'label of the action that triggered the path annotation',
    'logger': 'logger for reporting a message',
    'message': 'message (plus possible tsring expansion arguments)',
    'orig_request': 'original input by which a path was determined',
    'parentds':
        'path of dataset containing the annotated path (superdataset for subdatasets)',
    'path': 'absolute path that is annotated',
    'process_content': 'flag that content underneath the path is to be processed',
    'process_updated_only':
        'flag that only known dataset components are to be processed',
    'raw_input': 'flag whether this path was given as raw (non-annotated) input',
    'revision': 'the recorded commit for a subdataset in a superdataset',
    'revision_descr': 'a human-readable description of `revision`',
    'refds': 'path of a reference/base dataset the annotated path is part of',
    'registered_subds': 'flag whether a dataset is known to be a true subdataset of `parentds`',
    'source_url': 'URL a dataset was installed from',  # unify with `url`?
    'staged': 'flag whether a path is known to be "staged" in its containing dataset',
    'state':
        'state indicator for a path in its containing dataset (clean, modified, absent (also for files), conflict)',
    'status': 'action result status (ok, notneeded, impossible, error)',
    'type': 'nature of the path (file, directory, dataset)',
    'url': 'registered URL for a subdataset in a superdataset',  # unify with `source_url`?
}


@build_doc
class AnnotatePaths(Interface):
    """Analyze and act upon input paths

    Given paths (or more generally location requests) are inspected and
    annotated with a number of properties. A list of recognized properties
    is provided below.

    || PYTHON >>Input `paths` for this command can either be un-annotated
    (raw) path strings, or already (partially) annotated paths. In the latter
    case, further annotation is limited to yet-unknown properties, and is
    potentially faster than initial annotation.<< PYTHON ||


    *Recognized path properties*

    {proplist}

    In the case of enabled modification detection the results may contain
    additional properties regarding the nature of the modification. See the
    documentation of the `diff` command for details.

    """
    _docs_ = dict(
        proplist='\n\n    '.join(
            '"{}"\n{}'.format(
                k,
                textwrap.fill(known_props[k],
                              initial_indent='        ',
                              subsequent_indent='        '))
            for k in sorted(known_props)))

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to be annotated""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""an optional reference/base dataset for the paths""",
            constraints=EnsureDataset() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        action=Parameter(
            args=("--action",),
            metavar="LABEL",
            doc="""an "action" property value to include in the
            path annotation""",
            constraints=EnsureStr() | EnsureNone()),
        unavailable_path_status=Parameter(
            args=("--unavailable-path-status",),
            metavar="LABEL",
            doc="""a "status" property value to include in the
            annotation for paths that are underneath a dataset, but
            do not exist on the filesystem""",
            constraints=EnsureStr() | EnsureNone()),
        unavailable_path_msg=Parameter(
            args=("--unavailable-path-msg",),
            metavar="message",
            doc="""a "message" property value to include in the
            annotation for paths that are underneath a dataset, but
            do not exist on the filesystem""",
            constraints=EnsureStr() | EnsureNone()),
        nondataset_path_status=Parameter(
            args=("--nondataset-path-status",),
            metavar="LABEL",
            doc="""a "status" property value to include in the
            annotation for paths that are not underneath any dataset""",
            constraints=EnsureStr() | EnsureNone()),
        force_parentds_discovery=Parameter(
            args=("--no-parentds-discovery",),
            dest='force_parentds_discovery',
            action='store_false',
            doc="""Flag to disable reports of parent dataset information for any
            path, in particular dataset root paths. Disabling saves on command
            run time, if this information is not needed."""),
        force_subds_discovery=Parameter(
            args=("--no-subds-discovery",),
            action='store_false',
            dest='force_subds_discovery',
            doc="""Flag to disable reporting type='dataset' for subdatasets, even
            when they are not installed, or their mount point directory doesn't
            exist. Disabling saves on command run time, if this information is
            not needed."""),
        modified=Parameter(
            args=("--modified",),
            nargs='?',
            const=True,
            constraints=EnsureStr() | EnsureBool() | EnsureNone(),
            doc="""comparison reference specification for modification detection.
            This can be (mostly) anything that `git diff` understands (commit,
            treeish, tag, etc). See the documentation of `datalad diff --revision`
            for details. Unmodified paths will not be annotated. If a requested
            path was not modified but some content underneath it was, then the
            request is replaced by the modified paths and those are annotated
            instead. This option can be used without an argument to test against
            changes that have been made, but have not yet been staged for a
            commit."""))

    @staticmethod
    @datasetmethod(name='annotate_paths')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            action=None,
            unavailable_path_status='',
            unavailable_path_msg=None,
            nondataset_path_status='error',
            force_parentds_discovery=True,
            force_subds_discovery=True,
            modified=None):
        # upfront check for the fastest possible response
        if not path and dataset is None:
            # nothing given, try "here", but do not use `require_dataset`, as
            # it will determine the root dataset of `curdir` and further down
            # lead to path annotation of upstairs directories
            dataset = curdir

        if force_subds_discovery and not force_parentds_discovery:
            raise ValueError(
                'subdataset discovery requires parent dataset discovery')

        # CONCEPT: yield with no status to indicate further processing

        # everything in one big loop to be able too yield as fast a possible
        # without any precomputing for all paths

        refds_path = Interface.get_refds_path(dataset)
        if modified is not None and (refds_path is None or not GitRepo.is_valid_repo(refds_path)):
            raise ValueError(
                "modification detection only works with a base dataset (non-given or found)")

        # prep common result props
        res_kwargs = dict(
            action=action if action else 'annotate_path',
            refds=refds_path,
            logger=lgr)

        # handle the case of recursion into a single dataset without any
        # extra fancy processing first -- full recursion can be done
        # faster than manual recursion, hence we gain quite some speed
        # from these few lines of extra code
        if not modified and not path and refds_path:
            if not GitRepo.is_valid_repo(refds_path):
                yield get_status_dict(
                    # doesn't matter if the path is in another dataset
                    # it was given as reference dataset
                    status=nondataset_path_status,
                    message='given reference dataset is not a dataset',
                    path=refds_path,
                    **res_kwargs)
                return

            refds = Dataset(refds_path)
            path = []
            # yield the dataset itself
            r = get_status_dict(ds=refds, status='', **res_kwargs)
            yield r

            if recursive:
                # if we have nothing given, but need recursion, we need to feed
                # the dataset path itself
                for r in yield_recursive(
                        refds,
                        refds_path,
                        action,
                        recursion_limit):
                    r.update(res_kwargs)
                    if 'refds' in r and not r['refds']:
                        # avoid cruft
                        del r['refds']
                    yield r
            return

        # goal: structure in a way that makes most information on any path
        # available in a single pass, at the cheapest possible cost
        reported_paths = {}
        requested_paths = assure_list(path)

        if modified is not None:
            # replace the requested paths by those paths that were actually
            # modified underneath or at a requested location
            requested_paths = get_modified_subpaths(
                # either the request, or the base dataset, if there was no request
                requested_paths if requested_paths else [refds_path],
                refds=Dataset(refds_path),
                revision=modified)

        # do not loop over unique(), this could be a list of dicts
        # we avoid duplicates manually below via `reported_paths`
        for path in requested_paths:
            if not isinstance(path, dict):
                path = rawpath2ap(path, refds_path)
            # this is now an annotated path!
            path_props = path
            path = path['path']
            # we need to mark our territory, who knows where this has been
            path_props.update(res_kwargs)

            if path in reported_paths:
                # we already recorded this path in the output
                # this can happen, whenever `path` is a subdataset, that was
                # discovered via recursive processing of another path before
                continue
            # the path exists in some shape or form
            if isdir(path):
                # keep any existing type info, previously a more expensive run
                # could have discovered an uninstalled 'dataset', and we don't
                # want it to be relabeled to a directory
                path_props['type'] = \
                    path_props.get(
                        'type',
                        'dataset' if GitRepo.is_valid_repo(path) else 'directory')
                # this could contain all types of additional content
                containing_dir = path
            else:
                if lexists(path):
                    path_props['type'] = 'file'
                else:
                    path_props['state'] = 'absent'
                # for everything else we are interested in the container
                containing_dir = dirname(path)
                if not containing_dir:
                    containing_dir = curdir

            dspath = parent = get_dataset_root(containing_dir)
            if dspath:
                if path_props.get('type', None) == 'dataset':
                    # for a dataset the root is not the parent, for anything else
                    # it is
                    parent = path_props.get('parentds', None)
                    oneupdir = normpath(opj(containing_dir, pardir))
                    if parent is None and (force_parentds_discovery or (
                            refds_path and _with_sep(oneupdir).startswith(
                                _with_sep(refds_path)))):
                        # either forced, or only if we have a reference dataset, and
                        # only if we stay within this refds when searching for the
                        # parent
                        parent = get_dataset_root(normpath(opj(containing_dir, pardir)))
                        # NOTE the `and refds_path` is critical, as it will determine
                        # whether a top-level dataset that was discovered gets the
                        # parent property or not, it won't get it without a common
                        # base dataset, and that is how we always rolled
                    if parent and refds_path:
                        path_props['parentds'] = parent
                        # don't check whether this is actually a true subdataset of the
                        # parent, done further down
                else:
                    path_props['parentds'] = dspath

            # test for `dspath` not `parent`, we only need to know whether there is
            # ANY dataset, not which one is the true parent, logic below relies on
            # the fact that we end here, if there is no dataset at all
            if not dspath:
                # not in any dataset
                res = get_status_dict(
                    **dict(res_kwargs, **path_props))
                res['status'] = nondataset_path_status
                res['message'] = 'path not associated with any dataset'
                reported_paths[path] = res
                yield res
                continue

            # check that we only got SUBdatasets
            if refds_path and not _with_sep(dspath).startswith(_with_sep(refds_path)):
                res = get_status_dict(**dict(res_kwargs, **path_props))
                res['status'] = nondataset_path_status
                res['message'] = \
                    ('path not part of the reference dataset at %s', refds_path)
                reported_paths[path] = res
                yield res
                continue

            if path_props.get('type', None) == 'file':
                # nothing else we can learn about this
                res = get_status_dict(**dict(res_kwargs, **path_props))
                if 'status' not in res:
                    res['status'] = ''
                reported_paths[path] = res
                yield res
                continue

            containing_ds = None
            path_type = path_props.get('type', None)
            if parent and force_subds_discovery and (
                    (path_type == 'dataset' and 'registered_subds' not in path_props) or
                    path_type == 'directory' or
                    not lexists(path)):
                # if the path doesn't exist, or is labeled a directory, or a dataset even
                # a dataset (without this info) -> record whether this is a known subdataset
                # to its parent
                containing_ds = Dataset(parent)
                subdss = containing_ds.subdatasets(
                    fulfilled=None, recursive=False,
                    result_xfm=None, result_filter=None, return_type='list')
                if path in [s['path'] for s in subdss]:
                    if path_type == 'directory' or not lexists(path):
                        # first record that it isn't here, if just a dir or not here at all
                        path_props['state'] = 'absent'
                    # this must be a directory, and it is not installed
                    path_props['type'] = 'dataset'
                    path_props['registered_subds'] = True

            if not lexists(path):
                # not there (yet)
                message = unavailable_path_msg if unavailable_path_msg else None
                if message and '%s' in message:
                    message = (message, path)
                path_props['message'] = message
                res = get_status_dict(**dict(res_kwargs, **path_props))
                # assign given status, but only if the props don't indicate a status
                # already
                res['status'] = path_props.get(
                    'unavailable_path_status', unavailable_path_status)
                reported_paths[path] = res
                yield res
                continue

            # we know everything we can, report
            res = get_status_dict(**dict(res_kwargs, **path_props))
            if 'status' not in res:
                res['status'] = ''
            reported_paths[path] = res
            yield res

            rec_paths = []
            if recursive:
                # here we need to consider the special case that `path` is
                # a dataset itself, if a recursion_limit is given (e.g.
                # `remove` will do that by default), we need to recurse
                # from the dataset itself, and not its parent to get things
                # right -- this will also avoid needless discovery of
                # unrelated subdatasets
                if path_props.get('type', None) == 'dataset':
                    containing_ds = Dataset(path)
                else:
                    # regular parent, we might have a dataset already
                    containing_ds = Dataset(parent) if containing_ds is None else containing_ds
                for r in yield_recursive(containing_ds, path, action, recursion_limit):
                    # capture reported paths
                    r.update(res_kwargs)
                    if 'refds' in r and not r['refds']:
                        # avoid cruft
                        del r['refds']
                    reported_paths[r['path']] = r
                    if modified is not None:
                        # we cannot yield right away, maybe it wasn't modified
                        rec_paths.append(r)
                    else:
                        yield r
            if modified is not None and rec_paths:
                # replace the recursively discovered paths by those paths that
                # were actually modified underneath or at a requested location
                for r in get_modified_subpaths(
                        rec_paths,
                        refds=Dataset(refds_path),
                        revision=modified):
                    res = get_status_dict(**dict(r, **res_kwargs))
                    reported_paths[res['path']] = res
                    yield res
        return
