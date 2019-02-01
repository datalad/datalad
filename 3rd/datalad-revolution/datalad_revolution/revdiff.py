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
import os
import os.path as op
from six import (
    iteritems,
    text_type,
)
from collections import OrderedDict
from datalad.utils import (
    assure_list,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.utils import eval_results
from datalad.interface.common_opts import (
    recursion_limit,
    recursion_flag,
)

from .dataset import (
    RevolutionDataset as Dataset,
    EnsureRevDataset,
    rev_datasetmethod,
    require_rev_dataset,
    rev_resolve_path,
    path_under_rev_dataset,
    rev_get_dataset_root,
)
from . import utils as ut

from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
    EnsureChoice,
)
from datalad.support.param import Parameter
from datalad.consts import PRE_INIT_COMMIT_SHA

lgr = logging.getLogger('datalad.revolution.diff')


_common_diffstatus_params = dict(
    dataset=Parameter(
        args=("-d", "--dataset"),
        doc="""specify the dataset to query.  If
        no dataset is given, an attempt is made to identify the dataset
        based on the current working directory""",
        constraints=EnsureRevDataset() | EnsureNone()),
    annex=Parameter(
        args=('--annex',),
        metavar='MODE',
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
        """),
    untracked=Parameter(
        args=('--untracked',),
        metavar='MODE',
        constraints=EnsureChoice('no', 'normal', 'all'),
        doc="""If and how untracked content is reported when comparing
        a revision to the state of the work tree. 'no': no untracked
        content is reported; 'normal': untracked files and entire
        untracked directories are reported as such; 'all': report
        individual files even in fully untracked directories."""),
    recursive=recursion_flag,
    recursion_limit=recursion_limit)


@build_doc
class RevDiff(Interface):
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
            nargs=1,
            constraints=EnsureStr()),
        to=Parameter(
            args=("-t", "--to",),
            metavar="REVISION",
            doc="""state to compare against the original state, as given by
            any identifier that Git understands. If none is specified,
            the state of the worktree will be used compared.""",
            nargs=1,
            constraints=EnsureStr() | EnsureNone()),
    )

    @staticmethod
    @rev_datasetmethod(name='rev_diff')
    @eval_results
    def __call__(
            fr='HEAD',
            to=None,
            path=None,
            dataset=None,
            annex=None,
            untracked='normal',
            recursive=False,
            recursion_limit=None):
        ds = require_rev_dataset(
            dataset, check_installed=True, purpose='difference reporting')

        # convert cmdline args into plain labels
        if isinstance(fr, list):
            fr = fr[0]
        if isinstance(to, list):
            to = to[0]

        for r in _diff_cmd(
                ds=ds,
                dataset=dataset,
                fr=fr,
                to=to,
                constant_refs=False,
                path=path,
                annex=annex,
                untracked=untracked,
                recursive=recursive,
                recursion_limit=recursion_limit):
            yield r

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: no cover
        if not (res['status'] == 'ok' \
                and res['action'] in ('status', 'diff') \
                and res.get('state', None) != 'clean'):
            # logging reported already
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
        state = res['state']
        ui.message('{fill}{state}: {path}{type_}'.format(
            fill=' ' * max(0, max_len - len(state)),
            state=ut.ac.color_word(
                state,
                ut.state_color_map.get(res['state'], ut.ac.WHITE)),
            path=path,
            type_=' ({})'.format(
                ut.ac.color_word(type_, ut.ac.MAGENTA) if type_ else '')))


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
        recursion_limit=None):
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
            orig_path = str(p)
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
            cache=content_info_cache):
        res.update(
            refds=ds.path,
            logger=lgr,
            action='diff',
        )
        yield res


def _diff_ds(ds, fr, to, constant_refs, recursion_level, origpaths, untracked,
             annexinfo, cache):
    if not ds.repo:
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
            ignore_submodules='other',
            _cache=cache)
    except ValueError as e:
        msg_tmpl = "reference '{}' invalid"
        # not looking for a debug repr of the exception, just the message
        estr = str(e)
        if msg_tmpl.format(fr) in estr or msg_tmpl.format(to) in estr:
            yield dict(
                path=ds.path,
                status='impossible',
                message=estr,
            )
            return

    if annexinfo and hasattr(ds.repo, 'get_content_annexinfo'):
        # this will ammend `status`
        ds.repo.get_content_annexinfo(
            paths=paths if paths else None,
            init=diff_state,
            eval_availability=annexinfo in ('availability', 'all'),
            ref=to)
        if fr != to:
            ds.repo.get_content_annexinfo(
                paths=paths if paths else None,
                init=diff_state,
                eval_availability=annexinfo in ('availability', 'all'),
                ref=fr,
                key_prefix="prev_")

    for path, props in iteritems(diff_state):
        pathinds = str(ds.pathobj / path.relative_to(repo_path))
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
                        # subtract on level on the way down
                        recursion_level=recursion_level - 1,
                        origpaths=origpaths,
                        untracked=untracked,
                        annexinfo=annexinfo,
                        cache=cache):
                    yield r
            else:
                raise RuntimeError(
                    "Unexpected subdataset state '{}'. That sucks!".format(
                        subds_state))
