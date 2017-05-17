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
from os.path import relpath

from datalad.utils import unique
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
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
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
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset
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
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            torepoadd = []
            respath_by_status = {}
            for ap in content_by_ds[ds_path]:
                # we have a new story
                ap.pop('status', None)
                torepoadd.append(ap['path'])

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
                torepoadd.append(gitmodules_path)
                # and for save
                content_by_ds[ds_path].append(dict(
                    path=gitmodules_path,
                    parentds=ds_path,
                    type='file'))
            # make sure any last minute additions make it to the saving stage
            # XXX? should content_by_ds become OrderedDict so that possible
            # super here gets processed last?
            # MIH: not sure WTF is going on, but if I don't create a new list
            # the content of `toadd` vanishes from the dict
            #content_by_ds[ds_path] = [a for a in torepoadd]
            lgr.debug('Adding content to repo %s: %s', ds.repo, torepoadd)
            added = ds.repo.add(
                torepoadd,
                git=to_git if isinstance(ds.repo, AnnexRepo) else True,
                commit=False)
            for a in added:
                if a['file'] == '.gitmodules':
                    # filter out .gitmodules, because this is only included for
                    # technical reasons and has nothing to do with the actual content
                    continue
                res = annexjson2result(a, ds, type='file', **common_report)
                # TODO pull out correct ap for any path that comes out here
                # (that we know things about), and use the original annotation
                # instead of the annex report
                if GitRepo.is_valid_repo(res['path']):
                    # more accurate report in case of an added submodule
                    # mountpoint.
                    # XXX Actually not sure if this can really happen
                    # (depends on what our low-level code would do)
                    # but worst case is that we loose a little bit of
                    # coverage...
                    res['type'] = 'dataset'
                    res['message'] = 'added new state as submodule'
                success = success_status_map[res['status']]
                respath_by_status[success] = \
                    respath_by_status.get(success, []) + [res['path']]
                yield res

            # TODO pull out correct ap for any path that comes out here
            # (that we know things about), and use the original annotation
            # instead of the annex report
            for r in results_from_annex_noinfo(
                    ds, torepoadd, respath_by_status,
                    dir_fail_msg='could not add some content in %s %s',
                    noinfo_dir_msg='nothing to add from %s',
                    noinfo_file_msg='already included in the dataset',
                    action='add',
                    logger=lgr,
                    refds=refds_path):
                yield r

        if not save:
            lgr.debug('Not calling `save` as instructed')
            return

        # OPT: tries to save even unrelated stuff
        # MIH: issue reference would help to evaluate this comment!
        # TODO check what ap are coming down here, when save can accept
        # them to finally become more clever deciding what to save
        for res in save_dataset_hierarchy(
                # TODO RF pass annotated paths when receiver is ready
                #content_by_ds,
                {dspath: [p['path'] if isinstance(p, dict) else p
                          for p in content_by_ds[dspath]]
                 for dspath in content_by_ds},
                base=dataset.path if dataset and dataset.is_installed() else None,
                message=message if message else '[DATALAD] added content'):
            yield res
