# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding dataset components

"""

import logging

from os import listdir
from os.path import isdir
from os.path import join as opj
from os.path import normpath
from os.path import pardir
from os.path import relpath

from datalad.utils import unique
from datalad.utils import get_dataset_root
from datalad.interface.base import Interface
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import save_message_opt
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_add_opts
from datalad.interface.common_opts import jobs_opt
from datalad.interface.results import get_status_dict
from datalad.interface.results import annexjson2result
from datalad.interface.results import success_status_map
from datalad.interface.results import results_from_annex_noinfo
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.save import Save
from datalad.distribution.utils import _fixup_submodule_dotgit_setup
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import CommandError

from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import Dataset


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.add')


def _discover_subdatasets_recursively(
        discovered, top, trace, recursion_limit):
    # this beast walks the directory tree from a give `top` directory
    # and discovers valid repos that are scattered around, regardless
    # of whether they are already subdatasets or not
    # `trace` must be a list that has at least one element (the base
    # dataset)
    if recursion_limit is not None and len(trace) > recursion_limit:
        return
    if not isdir(top):
        return
    if GitRepo.is_valid_repo(top):
        if top in discovered:
            # this was found already, assume everythin beneath it too
            return
        discovered[top] = dict(
            path=top,
            # and its content
            process_content=True,
            type='dataset',
            parentds=trace[-1])
        # new node in the trace down
        trace = trace + [top]
    for path in listdir(top):
        path = opj(top, path)
        if not isdir(path):
            continue
        # next level down
        _discover_subdatasets_recursively(
            discovered, path, trace, recursion_limit)


@build_doc
class Add(Interface):
    """Add files/directories to an existing dataset.

    Typically, files and directories to be added to a dataset would be placed
    into a directory of a dataset, and subsequently this command can be used to
    register this new content with the dataset. With recursion enabled,
    files will be added to their respective subdatasets as well.

    || REFLOW >>
    By default all files are added to the dataset's :term:`annex`, i.e. only
    their content identity and availability information is tracked with Git.
    This results in lightweight datasets. If desired, the [PY: `to_git`
    PY][CMD: --to-git CMD] flag can be used to tell datalad to inject files
    directly into Git. While this is not recommended for binary data or large
    files, it can be used for source code and meta-data to be able to benefit
    from Git's track and merge capabilities. Files checked directly into Git
    are always and unconditionally available immediately after installation of
    a dataset.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git annex add`, or
      :command:`git add` to incorporate new dataset content.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to perform the add operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name of the component to be added. The component
            must either exist on the filesystem already, or a `source`
            has to be provided.""",
            nargs="+",
            constraints=EnsureStr() | EnsureNone()),
        to_git=Parameter(
            args=("--to-git",),
            action='store_true',
            doc="""flag whether to add data directly to Git, instead of
            tracking data identity only.  Usually this is not desired,
            as it inflates dataset sizes and impacts flexibility of data
            transport. If not specified - it will be up to git-annex to
            decide, possibly on .gitattributes options."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        # TODO not functional anymore
        ds2super=Parameter(
            args=("-S", "--ds2super", "--datasets-to-super",),
            action='store_true',
            doc="""given paths of dataset (toplevel) locations will cause
            these datasets to be added to their respective superdatasets
            underneath a given base `dataset` (instead of all their content
            to themselves). If no base `dataset` is provided, this flag has
            no effect. Regular files and directories are always added to
            their respective datasets, regardless of this setting."""),
        save=nosave_opt,
        message=save_message_opt,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_add_opts=annex_add_opts,
        jobs=jobs_opt
    )

    @staticmethod
    @datasetmethod(name='add')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            # support passing this through in a path by path basis
            to_git=None,
            save=True,
            message=None,
            recursive=False,
            recursion_limit=None,
            ds2super=False,
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None,
            jobs=None):

        # parameter constraints:
        if not path:
            raise InsufficientArgumentsError(
                "insufficient information for adding: requires at least a path")
        refds_path = Interface.get_refds_path(dataset)
        common_report = dict(action='add', logger=lgr, refds=refds_path)

        to_add = []
        subds_to_add = {}
        ds_to_annotate_from_recursion = {}
        for ap in AnnotatePaths.__call__(
                path=path,
                dataset=dataset,
                # never recursion, need to handle manually below to be able to
                # discover untracked content
                recursive=False,
                action='add',
                unavailable_path_status='impossible',
                unavailable_path_msg="path does not exist: %s",
                nondataset_path_status='impossible',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('parentds', None) is None and ap.get('type', None) != 'dataset':
                yield get_status_dict(
                    status='impossible',
                    message='"there is no dataset to add this path to',
                    **dict(common_report, **ap))
                continue
            if ap.get('raw_input', False) and recursive and (
                    ap.get('parentds', None) or ap.get('type', None) == 'dataset'):
                # this was an actually requested input path
                # we need to recursive into all subdirs to find potentially
                # unregistered subdatasets
                # but only if this path has a parent, or is itself a dataset
                # otherwise there is nothing to add to
                _discover_subdatasets_recursively(
                    ds_to_annotate_from_recursion,
                    ap['path'], [ap['parentds'] if 'parentds' in ap else ap['path']],
                    recursion_limit)
            # record for further processing
            if not ap['path'] in ds_to_annotate_from_recursion:
                # if it was somehow already discovered
                to_add.append(ap)
            # TODO check if next isn't covered by discover_dataset_trace_to_targets already??
            if dataset and ap.get('type', None) == 'dataset':
                # duplicates not possible, annotated_paths returns unique paths
                subds_to_add[ap['path']] = ap
        for subds in ds_to_annotate_from_recursion:
            if subds not in subds_to_add:
                # always prefer the already annotated path
                subds_to_add[subds] = ds_to_annotate_from_recursion[subds]

        if dataset:
            # we have a base dataset, discover any intermediate datasets between
            # the base and any already discovered dataset
            discovered = {}
            discover_dataset_trace_to_targets(
                # from here
                dataset.path,
                # to any dataset we are aware of
                subds_to_add.keys(),
                [],
                discovered)
            for parentds in discovered:
                for subds in discovered[parentds]:
                    subds_to_add[subds] = subds_to_add.get(
                        subds,
                        dict(path=subds, parentds=parentds, type='dataset'))

        # merge custom paths and discovered dataset records, paths needs to go first,
        # because we know most about then, and subsequent annotation call we skip the
        # later duplicate ones
        to_add.extend(subds_to_add.values())
        # and compact, this should be OK as all the info is in each ap dict
        to_add = unique(to_add, lambda x: x['path'])

        if not to_add:
            # nothing left to do, potentially all errored before
            return

        # now re-annotate all paths, this will be fast for already annotated ones
        # and will amend the annotation for others, it will also deduplicate
        annotated_paths = AnnotatePaths.__call__(
            path=to_add,
            dataset=dataset,
            # never recursion, done already
            recursive=False,
            action='add',
            unavailable_path_status='impossible',
            unavailable_path_msg="path does not exist: %s",
            nondataset_path_status='impossible',
            return_type='generator',
            # if there is an error now, we made this mistake in here
            on_failure='stop')

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                annotated_paths,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        if not content_by_ds:
            # we should have complained about any inappropriate path argument
            # above, so if nothing is left, we can simply exit
            return

        # simple loop over datasets -- save happens later
        # start deep down
        to_save = []
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            torepoadd = {}
            respath_by_status = {}
            for ap in content_by_ds[ds_path]:
                # we have a new story
                ap.pop('status', None)
                torepoadd[ap['path']] = ap

                # skip anything that doesn't look like a wannabe subdataset
                if not ap.get('type', None) == 'dataset' or \
                        ap['path'] == ds_path:
                    continue

                if ap.get('registered_subds', False):
                    # subdataset that might be in this list because of the
                    # need to save all the way up to a super dataset
                    respath_by_status['success'] = \
                        respath_by_status.get('success', []) + [ap['path']]
                    yield get_status_dict(
                        status='notneeded',
                        message="already known subdataset",
                        **dict(common_report, **ap))
                    continue
                subds = Dataset(ap['path'])
                # check that the subds has a commit, and refuse
                # to operate on it otherwise, or we would get a bastard
                # submodule that cripples git operations
                if not subds.repo.get_hexsha():
                    yield get_status_dict(
                        ds=subds, status='impossible',
                        message='cannot add subdataset with no commits',
                        **dict(common_report, **ap))
                    continue
                subds_relpath = relpath(ap['path'], ds_path)
                # make an attempt to configure a submodule source URL based on the
                # discovered remote configuration
                remote, branch = subds.repo.get_tracking_branch()
                subds_url = subds.repo.get_remote_url(remote) if remote else None
                # Register the repository in the repo tree as a submodule
                try:
                    ds.repo.add_submodule(subds_relpath, url=subds_url, name=None)
                except CommandError as e:
                    yield get_status_dict(
                        ds=subds, status='error', message=e.stderr,
                        **dict(common_report, **ap))
                    continue
                # queue for saving using the updated annotated path
                ap['registered_subds'] = True
                # I hope this is true in direct mode too
                # TODO this is disabled, because in some circumstances
                # staging just doesn't happen, and it is unclear when
                # exactly -- the case that prompted disabling was a submodule
                # that had no content except for other submodules was not staged,
                # whereas another submodule on the same level in the same
                # superdataset which also has one file in it was staged
                # disable to work correctly, while paying a little bit of
                # slow down
                #ap['staged'] = True
                to_save.append(ap)
                _fixup_submodule_dotgit_setup(ds, subds_relpath)
                # report added subdatasets -- `annex add` below won't do it
                yield get_status_dict(
                    ds=subds,
                    status='ok',
                    message='added new subdataset',
                    **dict(common_report, **ap))
                # make sure that .gitmodules is added to the list of files
                gitmodules_path = opj(ds.path, '.gitmodules')
                # for git
                torepoadd[gitmodules_path] = dict(path=gitmodules_path)
                # and for save
                to_save.append(dict(
                    path=gitmodules_path,
                    parentds=ds_path,
                    type='file'))
            # make sure any last minute additions make it to the saving stage
            # XXX? should content_by_ds become OrderedDict so that possible
            # super here gets processed last?
            lgr.debug('Adding content to repo %s: %s', ds.repo, torepoadd)
            added = ds.repo.add(
                list(torepoadd.keys()),
                git=to_git if isinstance(ds.repo, AnnexRepo) else True,
                commit=False)
            for a in added:
                res = annexjson2result(a, ds, type='file', **common_report)
                success = success_status_map[res['status']]
                respath_by_status[success] = \
                    respath_by_status.get(success, []) + [res['path']]
                # produce best possible path/result annotation
                if res['path'] in torepoadd:
                    # pull out correct ap for any path that comes out here
                    # (that we know things about), and use the original annotation
                    # instead of just the annex report
                    res = dict(torepoadd[res['path']], **res)
                # override this in all cases to be safe
                res['parentds'] = ds.path
                if success:
                    # this was successfully added, queue for saving this very path
                    # in the dataset
                    ap = {k: v for k, v in res.items() if k != 'status'}
                    ap['staged'] = True
                    to_save.append({k: v for k, v in res.items() if k != 'status'})
                if a['file'] == '.gitmodules':
                    # filter out .gitmodules, because this is only included for
                    # technical reasons and has nothing to do with the actual content
                    continue
                if GitRepo.is_valid_repo(res['path']):
                    # more accurate report in case of an added submodule
                    # mountpoint.
                    # XXX Actually not sure if this can really happen
                    # (depends on what our low-level code would do)
                    # but worst case is that we loose a little bit of
                    # coverage...
                    res['type'] = 'dataset'
                    res['message'] = 'added new state as submodule'
                yield res

            for r in results_from_annex_noinfo(
                    ds, torepoadd, respath_by_status,
                    dir_fail_msg='could not add some content in %s %s',
                    noinfo_dir_msg='nothing to add from %s',
                    noinfo_file_msg='already included in the dataset',
                    action='add',
                    logger=lgr,
                    refds=refds_path):
                if r['path'] in torepoadd:
                    # pull out correct ap for any path that comes out here
                    # (that we know things about), and use the original annotation
                    # instead of just the annex report
                    r = dict(torepoadd[r['path']], **r)

                # XXX something is fishy with the next one, rethink when sober....
                if r['path'] == ds_path and r['status'] == 'ok':
                    # this is for the entire dataset itself which was explicitly requested
                    # make sure to save all
                    r['type'] = 'dataset'
                    r['process_content'] = True
                    to_save.append({k: v for k, v in r.items() if k != 'status'})
                yield r
            if refds_path and ds_path != refds_path and len(respath_by_status.get('success', [])):
                # TODO XXX we have an issue here when with `add('.')` and annex ignores any
                # dotfiles. In this case we end up not saving a dataset completely, because
                # we rely on accurate reporting. there is an issue about this already
                # TODO look up the issue ID
                # if there is a base dataset, but we are below it, and we have anything done to this
                # dataset -> queue dataset itself for saving its state in the parent
                ds_ap = dict(
                    path=ds.path,
                    # we have to look for the parent here, as we must save the
                    # subdataset in the parent and not the whole subdataset itself
                    type='dataset')
                parentds = get_dataset_root(normpath(opj(ds.path, pardir)))
                if parentds:
                    ds_ap['parentds'] = parentds
                if dataset:
                    ds_ap['refds'] = refds_path
                to_save.append(ds_ap)

        if not save:
            lgr.debug('Not calling `save` as instructed')
            return

        # TODO tell save what was staged already! Set 'staged=True' for
        # respective annotated paths that are fed into `save`

        # do not reuse any of the sorting done in here for saving, but instead
        # pass on all the annotated paths to have `save` figure out what to do with
        # them -- this is costs something, but should be safer, and frankly is
        # more comprehensible
        for res in Save.__call__(
                # hand-selected annotated paths
                files=to_save,
                dataset=refds_path,
                message=message if message else '[DATALAD] added content',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
