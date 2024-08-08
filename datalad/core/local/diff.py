# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Report differences between two states of a dataset (hierarchy)"""

__docformat__ = 'restructuredtext'


import logging
import os.path as op

from datalad.core.local.status import (
    Status,
    _common_diffstatus_params,
)
from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
    path_under_rev_dataset,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import InvalidGitReferenceError
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    ensure_unicode,
    get_dataset_root,
)

lgr = logging.getLogger('datalad.core.local.diff')


@build_doc
class Diff(Interface):
    """Report differences between two states of a dataset (hierarchy)

    The two to-be-compared states are given via the --from and --to options.
    These state identifiers are evaluated in the context of the (specified
    or detected) dataset. In the case of a recursive report on a dataset
    hierarchy, corresponding state pairs for any subdataset are determined
    from the subdataset record in the respective superdataset. Only changes
    recorded in a subdataset between these two states are reported, and so on.

    Any paths given as additional arguments will be used to constrain the
    difference report. As with Git's diff, it will not result in an error when
    a path is specified that does not exist on the filesystem.

    Reports are very similar to those of the `status` command, with the
    distinguished content types and states being identical.
    """
    # make the custom renderer the default one, as the global default renderer
    # does not yield meaningful output for this command
    result_renderer = 'tailored'

    _params_ = dict(
        _common_diffstatus_params,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to constrain the report to""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        fr=Parameter(
            args=("-f", "--from",),
            dest='fr',
            metavar="REVISION",
            doc="""original state to compare to, as given by any identifier
            that Git understands.""",
            constraints=EnsureStr()),
        to=Parameter(
            args=("-t", "--to",),
            metavar="REVISION",
            doc="""state to compare against the original state, as given by
            any identifier that Git understands. If none is specified,
            the state of the working tree will be compared.""",
            constraints=EnsureStr() | EnsureNone()),
    )

    _examples_ = [
        dict(text="Show unsaved changes in a dataset",
             code_py="diff()",
             code_cmd="datalad diff"),
        dict(text="Compare a previous dataset state identified by shasum "
                  "against current worktree",
             code_py="diff(fr='SHASUM')",
             code_cmd="datalad diff --from <SHASUM>"),
        dict(text="Compare two branches against each other",
             code_py="diff(fr='branch1', to='branch2')",
             code_cmd="datalad diff --from branch1 --to branch2"),
        dict(text="Show unsaved changes in the dataset and potential subdatasets",
             code_py="diff(recursive=True)",
             code_cmd="datalad diff -r"),
        dict(text="Show unsaved changes made to a particular file",
             code_py="diff(path='path/to/file')",
             code_cmd="datalad diff <path/to/file>"),
    ]

    @staticmethod
    @datasetmethod(name='diff')
    @eval_results
    def __call__(
            path=None,
            *,
            fr='HEAD',
            to=None,
            dataset=None,
            annex=None,
            untracked='normal',
            recursive=False,
            recursion_limit=None):
        yield from diff_dataset(
            dataset=dataset,
            fr=ensure_unicode(fr),
            to=ensure_unicode(to),
            constant_refs=False,
            path=path,
            annex=annex,
            untracked=untracked,
            recursive=recursive,
            recursion_limit=recursion_limit)

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: more cover
        Status.custom_result_renderer(res, **kwargs)


def diff_dataset(
        dataset,
        fr,
        to,
        constant_refs,
        path=None,
        annex=None,
        untracked='normal',
        recursive=False,
        recursion_limit=None,
        reporting_order='depth-first',
        datasets_only=False,
):
    """Internal helper to diff a dataset

    Parameters
    ----------
    dataset : Dataset
      Dataset to perform the diff on. `fr` and `to` parameters are interpreted
      in the context of this dataset.
    fr : str
      Commit-ish to compare from.
    to : str
      Commit-ish to compare to.
    constant_refs : bool
      If True, `fr` and `to` will be passed on unmodified to diff operations
      on subdatasets. This can be useful with symbolic references like tags
      to report subdataset changes independent of superdataset changes.
      If False, `fr` and `to` will be translated to the subdataset commit-ish
      that match the given commit-ish in the superdataset.
    path : Path-like, optional
      Paths to constrain the diff to (see main diff() command).
    annex : str, optional
      Reporting mode for annex properties (see main diff() command).
    untracked : str, optional
      Reporting mode for untracked content (see main diff() command).
    recursive : bool, optional
      Flag to enable recursive operation (see main diff() command).
    recursion_limit : int, optional
      Recursion limit (see main diff() command).
    reporting_order : {'depth-first', 'breadth-first', 'bottom-up'}, optional
      By default, subdataset content records are reported after the record
      on the subdataset's submodule in a superdataset (depth-first).
      Alternatively, report all superdataset records first, before reporting
      any subdataset content records (breadth-first). Both 'depth-first'
      and 'breadth-first' both report dataset content before considering
      subdatasets. Alternative 'bottom-up' mode is similar to 'depth-first'
      but dataset content is reported after reporting on subdatasets.
    datasets_only : bool, optional
      Consider only changes to (sub)datasets but limiting operation only to
      paths of subdatasets.
      Note: ATM incompatible with explicit specification of `path`.

    Yields
    ------
    dict
      DataLad result records.
    """
    if reporting_order not in ('depth-first', 'breadth-first', 'bottom-up'):
        raise ValueError('Unknown reporting order: {}'.format(reporting_order))

    ds = require_dataset(
        dataset, check_installed=True, purpose='report difference')

    # we cannot really perform any sorting of paths into subdatasets
    # or rejecting paths based on the state of the filesystem, as
    # we need to be able to compare with states that are not represented
    # in the worktree (anymore)
    if path:
        if datasets_only:
            raise NotImplementedError(
                "Analysis of provided paths in datasets_only mode is not implemented"
            )

        ps = []
        # sort any path argument into the respective subdatasets
        for p in sorted(ensure_list(path)):
            # it is important to capture the exact form of the
            # given path argument, before any normalization happens
            # distinguish rsync-link syntax to identify
            # a dataset as whole (e.g. 'ds') vs its
            # content (e.g. 'ds/')
            # special case is the root dataset, always report its content
            # changes
            orig_path = str(p)
            resolved_path = resolve_path(p, dataset)
            p = \
                resolved_path, \
                orig_path.endswith(op.sep) or resolved_path == ds.pathobj
            str_path = str(p[0])
            root = get_dataset_root(str_path)
            if root is None:
                # no root, not possibly underneath the refds
                yield dict(
                    action='status',
                    path=str_path,
                    refds=ds.path,
                    status='error',
                    message='path not underneath this dataset',
                    logger=lgr)
                continue
            if path_under_rev_dataset(ds, str_path) is None:
                # nothing we support handling any further
                # there is only a single refds
                yield dict(
                    path=str_path,
                    refds=ds.path,
                    action='diff',
                    status='error',
                    message=(
                        "dataset containing given paths is not underneath "
                        "the reference dataset %s: %s",
                        ds, str_path),
                    logger=lgr,
                )
                continue

            ps.append(p)
        path = ps

    # TODO we might want to move away from the single-pass+immediate-yield
    # paradigm for this command. If we gather all information first, we
    # could do post-processing and detect when a file (same gitsha, or same
    # key) was copied/moved from another dataset. Another command (e.g.
    # save) could act on this information and also move/copy
    # availability information or at least enhance the respective commit
    # message with cross-dataset provenance info

    # cache to help avoid duplicate status queries
    content_info_cache = {}
    for res in _diff_ds(
            ds,
            fr,
            to,
            constant_refs,
            recursion_limit
            if recursion_limit is not None and recursive
            else -1 if recursive else 0,
            # TODO recode paths to repo path reference
            origpaths=None if not path else dict(path),
            untracked=untracked,
            annexinfo=annex,
            cache=content_info_cache,
            order=reporting_order,
            datasets_only=datasets_only,
    ):
        res.update(
            refds=ds.path,
            logger=lgr,
            action='diff',
        )
        yield res


def _diff_ds(ds, fr, to, constant_refs, recursion_level, origpaths, untracked,
             annexinfo, cache, order='depth-first', datasets_only=False):
    if not ds.is_installed():
        # asked to query a subdataset that is not available
        lgr.debug("Skip diff of unavailable subdataset: %s", ds)
        return

    repo = ds.repo
    repo_path = repo.pathobj
    if datasets_only:
        assert not origpaths  # protected above with NotImplementedError
        paths = dict(
            (sds.pathobj.relative_to(ds.pathobj), False)
            for sds in ds.subdatasets(
                recursive=False,
                state='present',
                result_renderer='disabled',
                result_xfm='datasets',
            )
        )
        if not paths:
            # no subdatasets, nothing todo???
            return
    else:
        # filter and normalize paths that match this dataset before passing them
        # onto the low-level query method
        paths = None if origpaths is None \
            else dict(
                (repo_path / p.relative_to(ds.pathobj), goinside)
                for p, goinside in origpaths.items()
                if ds.pathobj in p.parents or (p == ds.pathobj and goinside)
            )
    paths_arg = list(paths) if paths else None
    try:
        lgr.debug("Diff %s from '%s' to '%s'", ds, fr, to)
        diff_state = repo.diffstatus(
            fr,
            to,
            paths=paths_arg,
            untracked=untracked,
            eval_submodule_state='full' if to is None else 'commit',
            _cache=cache)
    except InvalidGitReferenceError as e:
        yield dict(
            path=ds.path,
            status='impossible',
            message=str(e),
        )
        return

    if annexinfo and hasattr(repo, 'get_content_annexinfo'):
        # this will amend `diff_state`
        repo.get_content_annexinfo(
            paths=paths_arg,
            init=diff_state,
            eval_availability=annexinfo in ('availability', 'all'),
            ref=to)
        # if `fr` is None, we compare against a preinit state, and
        # a get_content_annexinfo on that state doesn't get us anything new
        if fr and fr != to:
            repo.get_content_annexinfo(
                paths=paths_arg,
                init=diff_state,
                eval_availability=annexinfo in ('availability', 'all'),
                ref=fr,
                key_prefix="prev_")

    # potentially collect subdataset diff call specs for the end
    # (if order == 'breadth-first')
    ds_diffs = []
    subds_diffcalls = []
    for path, props in diff_state.items():
        pathinds = str(ds.pathobj / path.relative_to(repo_path))
        path_rec = dict(
            props,
            path=pathinds,
            # report the dataset path rather than the repo path to avoid
            # realpath/symlink issues
            parentds=ds.path,
            status='ok',
        )
        if order in ('breadth-first', 'depth-first'):
            yield path_rec
        elif order == 'bottom-up':
            ds_diffs.append(path_rec)
        else:
            raise ValueError(order)
        # for a dataset we need to decide whether to dive in, or not
        if props.get('type', None) == 'dataset' and (
                # subdataset path was given in rsync-style 'ds/'
                (paths and paths.get(path, False))
                # there is still sufficient recursion level left
                or recursion_level != 0
                # no recursion possible anymore, but one of the given
                # path arguments is in this subdataset
                or (recursion_level == 0
                    and paths
                    and any(path in p.parents for p in paths))):
            subds_state = props.get('state', None)
            if subds_state in ('clean', 'deleted'):
                # no need to look into the subdataset
                continue
            elif subds_state in ('added', 'modified'):
                # dive
                subds = Dataset(pathinds)
                call_args = (
                    subds,
                    # from before time or from the reported state
                    fr if constant_refs
                    else None
                    if subds_state == 'added'
                    else props['prev_gitshasum'],
                    # to the last recorded state, or the worktree
                    None if to is None
                    else to if constant_refs
                    else props['gitshasum'],
                    constant_refs,
                )
                call_kwargs = dict(
                    # subtract on level on the way down, unless the path
                    # args instructed to go inside this subdataset
                    recursion_level=recursion_level
                    # protect against dropping below zero (would mean unconditional
                    # recursion)
                    if not recursion_level or (paths and paths.get(path, False))
                    else recursion_level - 1,
                    origpaths=origpaths,
                    untracked=untracked,
                    annexinfo=annexinfo,
                    cache=cache,
                    order=order,
                    datasets_only=datasets_only,
                )
                if order in ('depth-first', 'bottom-up'):
                    yield from _diff_ds(*call_args, **call_kwargs)
                elif order == 'breadth-first':
                    subds_diffcalls.append((call_args, call_kwargs))
                else:
                    raise ValueError(order)
            else:
                raise RuntimeError(
                    "Unexpected subdataset state '{}'. That sucks!".format(
                        subds_state))
    # deal with staged ds diffs (for bottom-up)
    for rec in ds_diffs:
        yield rec
    # deal with staged subdataset diffs (for breadth-first)
    for call_args, call_kwargs in subds_diffcalls:
        yield from _diff_ds(*call_args, **call_kwargs)
