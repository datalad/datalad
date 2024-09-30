# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Report status of a dataset (hierarchy)'s work tree"""

__docformat__ = 'restructuredtext'


import logging
import os
import os.path as op
import warnings
from collections import OrderedDict

import datalad.support.ansi_colors as ac
import datalad.utils as ut
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    path_under_rev_dataset,
    require_dataset,
    resolve_path,
)
from datalad.dochelpers import single_or_plural
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.interface.utils import generic_result_renderer
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.utils import (
    bytes2human,
    ensure_list,
    ensure_unicode,
    get_dataset_root,
)

lgr = logging.getLogger('datalad.core.local.status')

_common_diffstatus_params = dict(
    dataset=Parameter(
        args=("-d", "--dataset"),
        doc="""specify the dataset to query.  If
        no dataset is given, an attempt is made to identify the dataset
        based on the current working directory""",
        constraints=EnsureDataset() | EnsureNone()),
    annex=Parameter(
        args=('--annex',),
        # the next two enable a sole `--annex` that auto-translates to
        # `--annex basic`
        const='basic',
        nargs='?',
        constraints=EnsureChoice(None, 'basic', 'availability', 'all'),
        doc="""Switch whether to include information on the annex
        content of individual files in the status report, such as
        recorded file size. By default no annex information is reported
        (faster). Three report modes are available: basic information
        like file size and key name ('basic'); additionally test whether
        file content is present in the local annex ('availability';
        requires one or two additional file system stat calls, but does
        not call git-annex), this will add the result properties
        'has_content' (boolean flag) and 'objloc' (absolute path to an
        existing annex object file); or 'all' which will report all
        available information (presently identical to 'availability').
        [CMD: The 'basic' mode will be assumed when this option is given,
        but no mode is specified. CMD]
        """),
    untracked=Parameter(
        args=('--untracked',),
        constraints=EnsureChoice('no', 'normal', 'all'),
        doc="""If and how untracked content is reported when comparing
        a revision to the state of the working tree. 'no': no untracked
        content is reported; 'normal': untracked files and entire
        untracked directories are reported as such; 'all': report
        individual files even in fully untracked directories."""),
    recursive=recursion_flag,
    recursion_limit=recursion_limit)


STATE_COLOR_MAP = {
    'untracked': ac.RED,
    'modified': ac.RED,
    'deleted': ac.RED,
    'added': ac.GREEN,
    'unknown': ac.YELLOW,
}


def yield_dataset_status(ds, paths, annexinfo, untracked, recursion_limit,
                         queried, eval_submodule_state, eval_filetype, cache,
                         reporting_order):
    """Internal helper to obtain status information on a dataset

    Parameters
    ----------
    ds : Dataset
      Dataset to get the status of.
    path : Path-like, optional
      Paths to constrain the status to (see main status() command).
    annexinfo : str
      Annex information reporting mode (see main status() command).
    untracked : str, optional
      Reporting mode for untracked content (see main status() command).
    recursion_limit : int, optional
    queried : set
      Will be populated with a Path instance for each queried dataset.
    eval_submodule_state : str
      Submodule evaluation mode setting for Repo.diffstatus().
    eval_filetype : bool, optional
      THIS OPTION IS IGNORED. It will be removed in a future release.
    cache : dict
      Cache to be passed on to all Repo.diffstatus() calls to avoid duplicate
      queries.
    reporting_order : {'depth-first', 'breadth-first'}, optional
      By default, subdataset content records are reported after the record
      on the subdataset's submodule in a superdataset (depth-first).
      Alternatively, report all superdataset records first, before reporting
      any subdataset content records (breadth-first).

    Yields
    ------
    dict
      DataLad result records.
    """
    if eval_filetype is not None:
        warnings.warn(
            "yield_dataset_status(eval_filetype=) no longer supported, "
            "and will be removed in a future release",
            DeprecationWarning)

    if reporting_order not in ('depth-first', 'breadth-first'):
        raise ValueError('Unknown reporting order: {}'.format(reporting_order))

    if ds.pathobj in queried:
        # do not report on a single dataset twice
        return
    # take the dataset that went in first
    repo = ds.repo
    repo_path = repo.pathobj
    lgr.debug('Querying %s.diffstatus() for paths: %s', repo, paths)
    # recode paths with repo reference for low-level API
    paths = [repo_path / p.relative_to(ds.pathobj) for p in paths] if paths else None
    status = repo.diffstatus(
        fr='HEAD' if repo.get_hexsha() else None,
        to=None,
        paths=paths,
        untracked=untracked,
        eval_submodule_state=eval_submodule_state,
        _cache=cache)
    if annexinfo and hasattr(repo, 'get_content_annexinfo'):
        if paths:
            # when an annex query has been requested for specific paths,
            # exclude untracked files from the annex query (else gh-7032)
            untracked = [k for k, v in status.items() if
                         v['state'] == 'untracked']
            lgr.debug(
                'Skipping %s.get_content_annexinfo() for untracked paths: %s',
                repo, paths)
            [paths.remove(p) for p in untracked]
        lgr.debug('Querying %s.get_content_annexinfo() for paths: %s', repo, paths)
        # this will amend `status`
        repo.get_content_annexinfo(
            paths=paths,
            init=status,
            eval_availability=annexinfo in ('availability', 'all'),
            ref=None)
    # potentially collect subdataset status call specs for the end
    # (if order == 'breadth-first')
    subds_statuscalls = []
    for path, props in status.items():
        cpath = ds.pathobj / path.relative_to(repo_path)
        yield dict(
            props,
            path=str(cpath),
            # report the dataset path rather than the repo path to avoid
            # realpath/symlink issues
            parentds=ds.path,
        )
        queried.add(ds.pathobj)
        if recursion_limit and props.get('type', None) == 'dataset':
            if cpath == ds.pathobj:
                # ATM can happen if there is something wrong with this repository
                # We will just skip it here and rely on some other exception to bubble up
                # See https://github.com/datalad/datalad/pull/4526 for the usecase
                lgr.debug("Got status for itself, which should not happen, skipping %s", path)
                continue
            subds = Dataset(str(cpath))
            if subds.is_installed():
                call_args = (
                    subds,
                    None,
                    annexinfo,
                    untracked,
                    recursion_limit - 1,
                    queried,
                    eval_submodule_state,
                    None,
                    cache,
                )
                call_kwargs = dict(
                    reporting_order='depth-first',
                )
                if reporting_order == 'depth-first':
                    yield from yield_dataset_status(*call_args, **call_kwargs)
                else:
                    subds_statuscalls.append((call_args, call_kwargs))

    # deal with staged subdataset status calls
    for call_args, call_kwargs in subds_statuscalls:
        yield from yield_dataset_status(*call_args, **call_kwargs)


@build_doc
class Status(Interface):
    """Report on the state of dataset content.

    This is an analog to `git status` that is simultaneously crippled and more
    powerful. It is crippled, because it only supports a fraction of the
    functionality of its counter part and only distinguishes a subset of the
    states that Git knows about. But it is also more powerful as it can handle
    status reports for a whole hierarchy of datasets, with the ability to
    report on a subset of the content (selection of paths) across any number
    of datasets in the hierarchy.

    *Path conventions*

    All reports are guaranteed to use absolute paths that are underneath the
    given or detected reference dataset, regardless of whether query paths are
    given as absolute or relative paths (with respect to the working directory,
    or to the reference dataset, when such a dataset is given explicitly).
    Moreover, so-called "explicit relative paths" (i.e. paths that start with
    '.' or '..') are also supported, and are interpreted as relative paths with
    respect to the current working directory regardless of whether a reference
    dataset with specified.

    When it is necessary to address a subdataset record in a superdataset
    without causing a status query for the state _within_ the subdataset
    itself, this can be achieved by explicitly providing a reference dataset
    and the path to the root of the subdataset like so::

      datalad status --dataset . subdspath

    In contrast, when the state of the subdataset within the superdataset is
    not relevant, a status query for the content of the subdataset can be
    obtained by adding a trailing path separator to the query path (rsync-like
    syntax)::

      datalad status --dataset . subdspath/

    When both aspects are relevant (the state of the subdataset content
    and the state of the subdataset within the superdataset), both queries
    can be combined::

      datalad status --dataset . subdspath subdspath/

    When performing a recursive status query, both status aspects of subdataset
    are always included in the report.


    *Content types*

    The following content types are distinguished:

    - 'dataset' -- any top-level dataset, or any subdataset that is properly
      registered in superdataset
    - 'directory' -- any directory that does not qualify for type 'dataset'
    - 'file' -- any file, or any symlink that is placeholder to an annexed
      file when annex-status reporting is enabled
    - 'symlink' -- any symlink that is not used as a placeholder for an annexed
      file

    *Content states*

    The following content states are distinguished:

    - 'clean'
    - 'added'
    - 'modified'
    - 'deleted'
    - 'untracked'
    """
    # make the custom renderer the default one, as the global default renderer
    # does not yield meaningful output for this command
    result_renderer = 'tailored'
    _examples_ = [
        dict(text="Report on the state of a dataset",
             code_py="status()",
             code_cmd="datalad status"),
        dict(text="Report on the state of a dataset and all subdatasets",
             code_py="status(recursive=True)",
             code_cmd="datalad status -r"),
        dict(text="Address a subdataset record in a superdataset without "
                  "causing a status query for the state _within_ the subdataset "
                  "itself",
             code_py="status(dataset='.', path='mysubdataset')",
             code_cmd="datalad status -d . mysubdataset"),
        dict(text="Get a status query for the state within the subdataset "
                  "without causing a status query for the superdataset (using trailing "
                  "path separator in the query path):",
             code_py="status(dataset='.', path='mysubdataset/')",
             code_cmd="datalad status -d . mysubdataset/"),
        dict(text="Report on the state of a subdataset in a superdataset and "
                  "on the state within the subdataset",
             code_py="status(dataset='.', path=['mysubdataset', 'mysubdataset/'])",
             code_cmd="datalad status -d . mysubdataset mysubdataset/"),
        dict(text="Report the file size of annexed content in a dataset",
             code_py="status(annex=True)",
             code_cmd="datalad status --annex")
    ]

    _params_ = dict(
        _common_diffstatus_params,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to be evaluated""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        eval_subdataset_state=Parameter(
            args=("-e", "--eval-subdataset-state",),
            constraints=EnsureChoice('no', 'commit', 'full'),
            doc="""Evaluation of subdataset state (clean vs.
            modified) can be expensive for deep dataset hierarchies
            as subdataset have to be tested recursively for
            uncommitted modifications. Setting this option to
            'no' or 'commit' can substantially boost performance
            by limiting what is being tested. With 'no' no state
            is evaluated and subdataset result records typically do
            not contain a 'state' property.
            With 'commit' only a discrepancy of the HEAD commit
            shasum of a subdataset and the shasum recorded in the
            superdataset's record is evaluated,
            and the 'state' result property only reflects this
            aspect. With 'full' any other modification is considered
            too (see the 'untracked' option for further tailoring
            modification testing)."""),
        report_filetype=Parameter(
            args=("-t", "--report-filetype",),
            constraints=EnsureChoice('raw', 'eval', None),
            doc="""THIS OPTION IS IGNORED. It will be removed in a future
            release. Dataset component types are always reported
            as-is (previous 'raw' mode), unless annex-reporting is enabled
            with the [CMD: --annex CMD][PY: `annex` PY] option, in which
            case symlinks that represent annexed files will be reported
            as type='file'."""),
    )

    @staticmethod
    @datasetmethod(name='status')
    @eval_results
    def __call__(
            path=None,
            *,
            dataset=None,
            annex=None,
            untracked='normal',
            recursive=False,
            recursion_limit=None,
            eval_subdataset_state='full',
            report_filetype=None):
        if report_filetype is not None:
            warnings.warn(
                "status(report_filetype=) no longer supported, and will be removed "
                "in a future release",
                DeprecationWarning)

        # To the next white knight that comes in to re-implement `status` as a
        # special case of `diff`. There is one fundamental difference between
        # the two commands: `status` can always use the worktree as evident on
        # disk as a constraint (e.g. to figure out which subdataset a path is
        # in) `diff` cannot do that (everything need to be handled based on a
        # "virtual" representation of a dataset hierarchy).
        # MIH concludes that while `status` can be implemented as a special case
        # of `diff` doing so would complicate and slow down both `diff` and
        # `status`. So while the apparent almost code-duplication between the
        # two commands feels wrong, the benefit is speed. Any future RF should
        # come with evidence that speed does not suffer, and complexity stays
        # on a manageable level
        ds = require_dataset(
            dataset, check_installed=True, purpose='report status')
        ds_path = ds.path
        queried = set()
        content_info_cache = {}
        for res in _yield_paths_by_ds(ds, dataset, ensure_list(path)):
            if 'status' in res:
                # this is an error
                yield res
                continue
            for r in yield_dataset_status(
                    res['ds'],
                    res['paths'],
                    annex,
                    untracked,
                    recursion_limit
                    if recursion_limit is not None else -1
                    if recursive else 0,
                    queried,
                    eval_subdataset_state,
                    None,
                    content_info_cache,
                    reporting_order='depth-first'):
                if 'status' not in r:
                    r['status'] = 'ok'
                yield dict(
                    r,
                    refds=ds_path,
                    action='status',
                )

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: more cover
        if (res['status'] == 'ok' and res['action'] in ('status', 'diff')
                and res.get('state') == 'clean'):
            # this renderer will be silent for clean status|diff results
            return
        if res['status'] != 'ok' or res['action'] not in ('status', 'diff'):
            # whatever this renderer cannot account for, send to generic
            generic_result_renderer(res)
            return
        from datalad.ui import ui

        # when to render relative paths:
        #  1) if a dataset arg was given
        #  2) if CWD is the refds
        refds = res.get('refds', None)
        refds = refds if kwargs.get('dataset', None) is not None \
            or refds == os.getcwd() else None
        path = res['path'] if refds is None \
            else str(ut.Path(res['path']).relative_to(refds))
        type_ = res.get('type', res.get('type_src', ''))
        max_len = len('untracked')
        state = res.get('state', 'unknown')
        ui.message(u'{fill}{state}: {path}{type_}'.format(
            fill=' ' * max(0, max_len - len(state)),
            state=ac.color_word(
                state,
                STATE_COLOR_MAP.get(res.get('state', 'unknown'))),
            path=path,
            type_=' ({})'.format(
                ac.color_word(type_, ac.MAGENTA) if type_ else '')))

    @staticmethod
    def custom_result_summary_renderer(results):  # pragma: more cover
        # fish out sizes of annexed files. those will only be present
        # with --annex ...
        annexed = [
            (r.get('bytesize', None), r.get('has_content', None), r['path'])
            for r in results
            if r.get('action', None) == 'status' \
            and 'key' in r]
        if annexed:
            # convert to int and interrogate files with content but
            # with unknown size (e.g. for --relaxed URLs), and drop 'path'
            annexed = [
                (int(bytesize) if bytesize is not None else (
                    int(os.stat(path).st_size) if has_content else 0
                 ), has_content)
                for bytesize, has_content, path in annexed
            ]
            have_availability = any(a[1] is not None for a in annexed)
            total_size = bytes2human(sum(a[0] for a in annexed))
            # we have availability info encoded in the results
            from datalad.ui import ui
            if have_availability:
                ui.message(
                    "{} annex'd {} ({}/{} present/total size)".format(
                        len(annexed),
                        single_or_plural('file', 'files', len(annexed)),
                        bytes2human(sum(a[0] for a in annexed if a[1])),
                        total_size))
            else:
                ui.message(
                    "{} annex'd {} ({} recorded total size)".format(
                        len(annexed),
                        single_or_plural('file', 'files', len(annexed)),
                        total_size))
        if all(r.get('action', None) == 'status'
               and r.get('state', None) == 'clean'
               for r in results):
            from datalad.ui import ui
            ui.message("nothing to save, working tree clean")


def get_paths_by_ds(refds, dataset_arg, paths, subdsroot_mode='rsync'):
    """Resolve and sort any paths into their containing datasets

    Any path will be associated (sorted into) its nearest containing dataset.
    It is irrelevant whether or not a path presently exists on the file system.
    However, only datasets that exist on the file system are used for
    sorting/association -- known, but non-existent subdatasets are not
    considered.

    Parameters
    ----------
    refds: Dataset
    dataset_arg: Dataset or str or Path or None
      Any supported value given to a command's `dataset` argument. Given
      to `resolve_path()`.
    paths: list
      Any number of absolute or relative paths, in str-form or as
      Path instances, to be sorted into their respective datasets. See also
      the `subdsroot_mode` parameter.
    subdsroot_mode: {'rsync', 'super', 'sub'}
      Switch behavior for paths that are the root of a subdataset. By default
      ('rsync'), such a path is associated with its parent/superdataset,
      unless the path ends with a trailing directory separator, in which case
      it is sorted into the subdataset record (this resembles the path
      semantics of rsync, hence the label). In 'super' mode, the path is always
      placed with the superdataset record. Likewise, in 'sub' mode the path
      is always placed into the subdataset record.

    Returns
    -------
    dict, list
      The first return value is the main result, a dictionary with root
      directories of all discovered datasets as keys and a list of the
      associated paths inside these datasets as values.  Keys and values are
      normalized to be Path instances of absolute paths.
      The second return value is a list of all paths (again Path instances)
      that are not located underneath the reference dataset.
    """
    ds_path = refds.path
    paths_by_ds = dict()
    errors = []

    if not paths:
        # that was quick
        paths_by_ds[refds.pathobj] = None
        return paths_by_ds, errors

    # in order to guarantee proper path sorting, we first need to resolve all
    # of them (some may be str, some Path, some relative, some absolute)
    # step 1: normalize to unicode
    paths = map(ensure_unicode, paths)
    # step 2: resolve
    # for later comparison, we need to preserve the original value too
    paths = [(resolve_path(p, dataset_arg), str(p)) for p in paths]
    # OPT: store cache for dataset roots for each directory directly
    #      listed in paths, or containing the path (if file)
    roots_cache = {}
    # sort any path argument into the respective subdatasets
    # sort by comparing the resolved Path instances, this puts top-level
    # paths first, leading to their datasets to be injected into the result
    # dict first
    for p, orig_path in sorted(paths, key=lambda x: x[0]):
        # TODO (left from implementing caching OPT):
        # Logic here sounds duplicated with discover_dataset_trace_to_targets
        # and even get_tree_roots of save.
        str_p = str(p)

        # query get_dataset_root caching for repeated queries within the same
        # directory
        if p.is_dir():
            p_dir = str(p)
        else:  # symlink, file, whatnot - seems to match logic in get_dataset_root
            p_dir = str(p.parent)

        try:
            root = roots_cache[p_dir]
        except KeyError:
            root = roots_cache[p_dir] = get_dataset_root(p_dir)

        # to become the root of the dataset that contains the path in question
        # in the context of (same basepath) as the reference dataset
        qds_inrefds = None
        if root is not None:
            qds_inrefds = path_under_rev_dataset(refds, root)
        if root is None or qds_inrefds is None:
            # no root, not possibly underneath the refds
            # or root that is not underneath/equal the reference dataset root
            errors.append(p)
            continue

        if root != qds_inrefds:
            # try to recode the dataset path wrt to the reference
            # dataset
            # the path that it might have been located by could
            # have been a resolved path or another funky thing
            # the path this dataset was located by is not how it would
            # be referenced underneath the refds (possibly resolved
            # realpath) -> recode all paths to be underneath the refds
            p = qds_inrefds / p.relative_to(root)
            root = qds_inrefds

        # Note: Compare to Dataset(root).path rather
        # than root to get same path normalization.
        if root == str_p and not Dataset(root).path == ds_path and (
                subdsroot_mode == 'super' or (
                subdsroot_mode == 'rsync' and dataset_arg and
                not orig_path.endswith(op.sep))):
            # the given path is pointing to a subdataset
            # and we are either in 'super' mode, or in 'rsync' and found
            # rsync-link syntax to identify the dataset as whole
            # (e.g. 'ds') vs its content (e.g. 'ds/')
            root_dir = op.dirname(root)
            try:
                super_root = roots_cache[root_dir]
            except KeyError:
                super_root = roots_cache[root_dir] = get_dataset_root(root_dir)
            if super_root:
                # the dataset identified by the path argument
                # is contained in a superdataset, and no
                # trailing path separator was found in the
                # argument -> user wants to address the dataset
                # as a whole (in the superdataset)
                root = super_root

        root = ut.Path(root)
        ps = paths_by_ds.get(root, [])
        ps.append(p)
        paths_by_ds[root] = ps
    return paths_by_ds, errors


def _yield_paths_by_ds(refds, dataset_arg, paths):
    """Status-internal helper to yield get_paths_by_ds() items"""
    paths_by_ds, errors = get_paths_by_ds(refds, dataset_arg, paths)
    # communicate all the problems
    for e in errors:
        yield dict(
            path=str(e),
            action='status',
            refds=refds.path,
            status='error',
            message=('path not underneath the reference dataset %s',
                     refds.path),
            logger=lgr)

    while paths_by_ds:
        # gh-6566 advised replacement of OrderedDicts with dicts for performance
        # The previous qdspath, qpaths = paths_by_ds.popitem(last=False) used an
        # OrderedDict specific function (returns k, v in FIFO order). Below is a
        # less pretty replacement for this functionality with a pure dict
        qdspath = next(iter(paths_by_ds.keys()))
        qpaths = paths_by_ds.pop(qdspath)
        if qpaths and qdspath in qpaths:
            # this is supposed to be a full status query, save some
            # cycles sifting through the actual path arguments
            qpaths = []
        yield dict(ds=Dataset(qdspath), paths=qpaths)
