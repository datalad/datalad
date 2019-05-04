# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from six import (
    iteritems,
    text_type,
)
from collections import OrderedDict
from datalad.utils import (
    assure_list,
    assure_unicode,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.utils import eval_results

from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
    require_dataset,
    rev_resolve_path,
    path_under_rev_dataset,
    rev_get_dataset_root,
)

from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.consts import PRE_INIT_COMMIT_SHA

from datalad.core.local.status import (
    Status,
    _common_diffstatus_params,
)
from datalad.support.exceptions import (
    InvalidGitReferenceError,
)

lgr = logging.getLogger('datalad.core.local.diff')


@build_doc
class Diff(Interface):
    """Report differences between two states of a dataset (hierarchy)

    The two to-be-compared states are given via to --from and --to options.
    These state identifiers are evaluated in the context of the (specified
    or detected) dataset. In case of a recursive report on a dataset
    hierarchy corresponding state pairs for any subdataset are determined
    from the subdataset record in the respective superdataset. Only changes
    recorded in a subdataset between these two states are reported, and so on.

    Any paths given as additional arguments will be used to constrain the
    difference report. As with Git's diff, it will not result in an error when
    a path is specified that does not exist on the filesystem.

    Reports are very similar to those of the `rev-status` command, with the
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
            doc="""path to contrain the report to""",
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
            the state of the worktree will be used compared.""",
            constraints=EnsureStr() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='diff')
    @eval_results
    def __call__(
            path=None,
            fr='HEAD',
            to=None,
            dataset=None,
            annex=None,
            untracked='normal',
            recursive=False,
            recursion_limit=None):
        ds = require_dataset(
            dataset, check_installed=True, purpose='difference reporting')

        for r in _diff_cmd(
                ds=ds,
                dataset=dataset,
                fr=assure_unicode(fr),
                to=assure_unicode(to),
                constant_refs=False,
                path=path,
                annex=annex,
                untracked=untracked,
                recursive=recursive,
                recursion_limit=recursion_limit):
            yield r

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: no cover
        Status.custom_result_renderer(res, **kwargs)


def _diff_cmd(
        ds,
        dataset,
        fr,
        to,
        constant_refs,
        path=None,
        annex=None,
        untracked='normal',
        recursive=False,
        recursion_limit=None,
        eval_file_type=True):
    """Internal helper to actually run the command"""
    # we cannot really perform any sorting of paths into subdatasets
    # or rejecting paths based on the state of the filesystem, as
    # we need to be able to compare with states that are not represented
    # in the worktree (anymore)
    if path:
        ps = []
        # sort any path argument into the respective subdatasets
        for p in sorted(assure_list(path)):
            # it is important to capture the exact form of the
            # given path argument, before any normalization happens
            # distinguish rsync-link syntax to identify
            # a dataset as whole (e.g. 'ds') vs its
            # content (e.g. 'ds/')
            # special case is the root dataset, always report its content
            # changes
            orig_path = text_type(p)
            resolved_path = rev_resolve_path(p, dataset)
            p = \
                resolved_path, \
                orig_path.endswith(op.sep) or resolved_path == ds.pathobj
            str_path = text_type(p[0])
            root = rev_get_dataset_root(str_path)
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
    # rev-save) could act on this information and also move/copy
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
            origpaths=None if not path else OrderedDict(path),
            untracked=untracked,
            annexinfo=annex,
            eval_file_type=True,
            cache=content_info_cache):
        res.update(
            refds=ds.path,
            logger=lgr,
            action='diff',
        )
        yield res


def _diff_ds(ds, fr, to, constant_refs, recursion_level, origpaths, untracked,
             annexinfo, eval_file_type, cache):
    if not ds.is_installed():
        # asked to query a subdataset that is not available
        lgr.debug("Skip diff of unavailable subdataset: %s", ds)
        return

    repo_path = ds.repo.pathobj
    # filter and normalize paths that match this dataset before passing them
    # onto the low-level query method
    paths = None if origpaths is None \
        else OrderedDict(
            (repo_path / p.relative_to(ds.pathobj), goinside)
            for p, goinside in iteritems(origpaths)
            if ds.pathobj in p.parents or (p == ds.pathobj and goinside)
        )
    try:
        lgr.debug("diff %s from '%s' to '%s'", ds, fr, to)
        diff_state = ds.repo.diffstatus(
            fr,
            to,
            paths=None if not paths else [p for p in paths],
            untracked=untracked,
            eval_file_type=eval_file_type,
            _cache=cache)
    except InvalidGitReferenceError as e:
        yield dict(
            path=ds.path,
            status='impossible',
            message=text_type(e),
        )
        return

    if annexinfo and hasattr(ds.repo, 'get_content_annexinfo'):
        # this will ammend `status`
        ds.repo.get_content_annexinfo(
            paths=paths.keys() if paths is not None else paths,
            init=diff_state,
            eval_availability=annexinfo in ('availability', 'all'),
            ref=to)
        if fr != to:
            ds.repo.get_content_annexinfo(
                paths=paths.keys() if paths is not None else paths,
                init=diff_state,
                eval_availability=annexinfo in ('availability', 'all'),
                ref=fr,
                key_prefix="prev_")

    for path, props in iteritems(diff_state):
        pathinds = text_type(ds.pathobj / path.relative_to(repo_path))
        yield dict(
            props,
            path=pathinds,
            # report the dataset path rather than the repo path to avoid
            # realpath/symlink issues
            parentds=ds.path,
            status='ok',
        )
        # if a dataset, and given in rsync-style 'ds/' or with sufficient
        # recursion level left -> dive in
        if props.get('type', None) == 'dataset' and (
                (paths and paths.get(path, False)) or recursion_level != 0):
            subds_state = props.get('state', None)
            if subds_state in ('clean', 'deleted'):
                # no need to look into the subdataset
                continue
            elif subds_state in ('added', 'modified'):
                # dive
                subds = Dataset(pathinds)
                for r in _diff_ds(
                        subds,
                        # from before time or from the reported state
                        fr if constant_refs
                        else PRE_INIT_COMMIT_SHA
                        if subds_state == 'added'
                        else props['prev_gitshasum'],
                        # to the last recorded state, or the worktree
                        None if to is None
                        else to if constant_refs
                        else props['gitshasum'],
                        constant_refs,
                        # subtract on level on the way down, unless the path
                        # args instructed to go inside this subdataset
                        recursion_level=recursion_level
                        if paths and paths.get(path, False) else recursion_level - 1,
                        origpaths=origpaths,
                        untracked=untracked,
                        annexinfo=annexinfo,
                        eval_file_type=eval_file_type,
                        cache=cache):
                    yield r
            else:
                raise RuntimeError(
                    "Unexpected subdataset state '{}'. That sucks!".format(
                        subds_state))
