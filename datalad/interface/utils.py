# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface utility functions

"""

__docformat__ = 'restructuredtext'

import json
import logging
import sys
from os import listdir
from os.path import isdir
from os.path import join as opj
from os.path import (
    relpath,
    sep,
)
from time import time
from typing import TypeVar

import datalad.support.ansi_colors as ac
from datalad import cfg as dlcfg
from datalad.dochelpers import single_or_plural
from datalad.support.exceptions import CapturedException
from datalad.support.gitrepo import GitRepo
from datalad.ui import ui
# avoid import from API to not get into circular imports
from datalad.utils import (
    ensure_unicode,
    getargspec,
    path_is_subpath,
    path_startswith,
)
from datalad.utils import \
    with_pathsep as \
    _with_sep  # TODO: RF whenever merge conflict is not upon us

anInterface = TypeVar('anInterface', bound='Interface')

lgr = logging.getLogger('datalad.interface.utils')


# TODO remove
# only `drop` and `uninstall` are still using this
def handle_dirty_dataset(ds, mode, msg=None):
    """Detect and treat unsaved changes as instructed by `mode`

    Parameters
    ----------
    ds : Dataset or None
      Dataset to be inspected. Does nothing if `None`.
    mode : {'fail', 'ignore', 'save-before'}
      How to act upon discovering unsaved changes.
    msg : str or None
      Custom message to use for a potential commit.

    Returns
    -------
    None
    """
    if ds is None:
        # nothing to be handled
        return
    if msg is None:
        msg = '[DATALAD] auto-saved changes'

    # make sure that all pending changes (batched annex operations, etc.)
    # are actually reflected in Git
    if ds.repo:
        ds.repo.precommit()

    if mode == 'ignore':
        return
    elif mode == 'fail':
        if not ds.repo or ds.repo.dirty:
            raise RuntimeError('dataset {} has unsaved changes'.format(ds))
    elif mode == 'save-before':
        if not ds.is_installed():
            raise RuntimeError('dataset {} is not yet installed'.format(ds))
        from datalad.core.local.save import Save
        Save.__call__(dataset=ds, message=msg, updated=True)
    else:
        raise ValueError("unknown if-dirty mode '{}'".format(mode))


def get_tree_roots(paths):
    """Return common root paths for a set of paths

    This function determines the smallest set of common root
    paths and sorts all given paths under the respective
    root.

    Returns
    -------
    dict
      paths by root
    """
    paths_ws = [_with_sep(p) for p in paths]
    # sort all paths under their potential roots
    roots = {}
    # start from the top to get all paths down the line
    # and collate them into as few roots as possible
    for s in sorted(paths_ws):
        if any([s.startswith(r) for r in roots]):
            # this path is already covered by a known root
            continue
        # find all sub paths
        subs = [p for p in paths if p.startswith(s)]
        roots[s.rstrip(sep)] = subs
    return roots


# TODO(OPT)? YOH: from a cursory review seems like possibly an expensive function
# whenever many paths were provided (e.g. via shell glob).
# Might be worth testing on some usecase and py-spy'ing if notable portion
# of time is spent.
def discover_dataset_trace_to_targets(basepath, targetpaths, current_trace,
                                      spec, includeds=None):
    """Discover the edges and nodes in a dataset tree to given target paths

    Parameters
    ----------
    basepath : path
      Path to a start or top-level dataset. Really has to be a path to a
      dataset!
    targetpaths : list(path)
      Any non-zero number of paths that are termination points for the
      search algorithm. Can be paths to datasets, directories, or files
      (and any combination thereof).
    current_trace : list
      For a top-level call this should probably always be `[]`
    spec : dict
      `content_by_ds`-style dictionary that will receive information about the
      discovered datasets. Specifically, for each discovered dataset there
      will be an item with its path under the key (path) of the respective
      superdataset.
    includeds : sequence, optional
      Any paths given are treated as existing subdatasets, regardless of
      whether they can be found in the filesystem. Such subdatasets will appear
      under the key of the closest existing dataset in the `spec`.

    Returns
    -------
    None
      Function calls itself recursively and populates `spec` dict in-place.
      Keys are dataset paths, values are sets of subdataset paths
    """
    # convert to set for faster lookup
    includeds = includeds if isinstance(includeds, set) else \
        set() if includeds is None else set(includeds)
    # this beast walks the directory tree from a given `basepath` until
    # it discovers any of the given `targetpaths`
    # if it finds one, it commits any accumulated trace of visited
    # datasets on this edge to the spec
    valid_repo = GitRepo.is_valid_repo(basepath)
    if valid_repo:
        # we are passing into a new dataset, extend the dataset trace
        current_trace = current_trace + [basepath]
    # this edge is not done, we need to try to reach any downstream
    # dataset
    undiscovered_ds = set(t for t in targetpaths)  # if t != basepath)
    # whether anything in this directory matched a targetpath
    filematch = False
    if isdir(basepath):
        for p in listdir(basepath):
            p = ensure_unicode(opj(basepath, p))
            if not isdir(p):
                if p in targetpaths:
                    filematch = True
                # we cannot have anything below this one
                continue
            # OPT listdir might be large and we could have only few items
            # in `targetpaths` -- so traverse only those in spec which have
            # leading dir basepath
            # filter targets matching this downward path
            downward_targets = set(
                t for t in targetpaths if path_startswith(t, p))
            if not downward_targets:
                continue
            # remove the matching ones from the "todo" list
            undiscovered_ds.difference_update(downward_targets)
            # go one deeper
            discover_dataset_trace_to_targets(
                p, downward_targets, current_trace, spec,
                includeds=includeds if not includeds else includeds.intersection(
                    downward_targets))
    undiscovered_ds = [t for t in undiscovered_ds
                       if includeds and
                       path_is_subpath(t, current_trace[-1]) and
                       t in includeds]
    if filematch or basepath in targetpaths or undiscovered_ds:
        for i, p in enumerate(current_trace[:-1]):
            # TODO RF prepare proper annotated path dicts
            subds = spec.get(p, set())
            subds.add(current_trace[i + 1])
            spec[p] = subds
        if undiscovered_ds:
            spec[current_trace[-1]] = spec.get(current_trace[-1], set()).union(
                undiscovered_ds)


def get_result_filter(fx):
    """Wrap a filter into a helper to be able to accept additional
    arguments, if the filter doesn't support it already"""
    _fx = fx
    if fx and not getargspec(fx).keywords:
        def _fx(res, **kwargs):
            return fx(res)
    return _fx


def eval_results(wrapped):
    import warnings

    from datalad.interface.base import eval_results as eval_results_moved
    warnings.warn("datalad.interface.utils.eval_results is obsolete. "
                  "Use datalad.interface.base.eval_results instead",
                  DeprecationWarning)
    return eval_results_moved(wrapped)


def generic_result_renderer(res):
    if res.get('status', None) != 'notneeded':
        path = res.get('path', None)
        if path and res.get('refds'):
            try:
                path = relpath(path, res['refds'])
            except ValueError:
                # can happen, e.g., on windows with paths from different
                # drives. just go with the original path in this case
                pass
        ui.message('{action}({status}):{path}{type}{msg}{err}'.format(
            action=ac.color_word(
                res.get('action', '<action-unspecified>'),
                ac.BOLD),
            status=ac.color_status(res.get('status', '<status-unspecified>')),
            path=' {}'.format(path) if path else '',
            type=' ({})'.format(
                ac.color_word(res['type'], ac.MAGENTA)
            ) if 'type' in res else '',
            msg=' [{}]'.format(
                res['message'][0] % res['message'][1:]
                if isinstance(res['message'], tuple) else res[
                    'message'])
            if res.get('message', None) else '',
            err=ac.color_word(' [{}]'.format(
                res['error_message'][0] % res['error_message'][1:]
                if isinstance(res['error_message'], tuple) else res[
                    'error_message']), ac.RED)
            if res.get('error_message', None) and res.get('status', None) != 'ok' else ''))


# keep for legacy compatibility
default_result_renderer = generic_result_renderer


def render_action_summary(action_summary):
    ui.message("action summary:\n  {}".format(
        '\n  '.join('{} ({})'.format(
            act,
            ', '.join('{}: {}'.format(status, action_summary[act][status])
                      for status in sorted(action_summary[act])))
                    for act in sorted(action_summary))))


def _display_suppressed_message(nsimilar, ndisplayed, last_ts, final=False):
    # +1 because there was the original result + nsimilar displayed.
    n_suppressed = nsimilar - ndisplayed + 1
    if n_suppressed > 0:
        ts = time()
        # rate-limit update of suppression message, with a large number
        # of fast-paced results updating for each one can result in more
        # CPU load than the actual processing
        # arbitrarily go for a 2Hz update frequency -- it "feels" good
        if last_ts is None or final or (ts - last_ts > 0.5):
            ui.message('  [{} similar {} been suppressed; disable with datalad.ui.suppress-similar-results=off]'
                       .format(n_suppressed,
                               single_or_plural("message has",
                                                "messages have",
                                                n_suppressed, False)),
                       cr="\n" if final else "\r")
            return ts
    return last_ts


def _process_results(
        results,
        cmd_class,
        on_failure,
        action_summary,
        incomplete_results,
        result_renderer,
        result_log_level,
        allkwargs):
    # private helper pf @eval_results
    # loop over results generated from some source and handle each
    # of them according to the requested behavior (logging, rendering, ...)

    # used to track repeated messages in the generic renderer
    last_result = None
    # the timestamp of the last renderer result
    last_result_ts = None
    # counter for detected repetitions
    last_result_reps = 0
    # how many repetitions to show, before suppression kicks in
    render_n_repetitions = \
        dlcfg.obtain('datalad.ui.suppress-similar-results-threshold') \
            if sys.stdout.isatty() \
               and dlcfg.obtain('datalad.ui.suppress-similar-results') \
            else float("inf")

    for res in results:
        if not res or 'action' not in res:
            # XXX Yarik has to no clue on how to track the origin of the
            # record to figure out WTF, so he just skips it
            # but MIH thinks leaving a trace of that would be good
            lgr.debug('Drop result record without "action": %s', res)
            continue

        actsum = action_summary.get(res['action'], {})
        if res['status']:
            actsum[res['status']] = actsum.get(res['status'], 0) + 1
            action_summary[res['action']] = actsum
        ## log message, if there is one and a logger was given
        msg = res.get('message', None)
        # remove logger instance from results, as it is no longer useful
        # after logging was done, it isn't serializable, and generally
        # pollutes the output
        res_lgr = res.pop('logger', None)
        if msg and res_lgr:
            if isinstance(res_lgr, logging.Logger):
                # didn't get a particular log function, go with default
                res_lgr = getattr(
                    res_lgr,
                    default_logchannels[res['status']]
                    if result_log_level == 'match-status'
                    else result_log_level)
            msg = res['message']
            msgargs = None
            if isinstance(msg, tuple):
                msgargs = msg[1:]
                msg = msg[0]
            if 'path' in res:
                # result path could be a path instance
                path = str(res['path'])
                if msgargs:
                    # we will pass the msg for %-polation, so % should be doubled
                    path = path.replace('%', '%%')
                msg = '{} [{}({})]'.format(
                    msg, res['action'], path)
            if msgargs:
                # support string expansion of logging to avoid runtime cost
                try:
                    res_lgr(msg, *msgargs)
                except TypeError as exc:
                    raise TypeError(
                        "Failed to render %r with %r from %r: %s"
                        % (msg, msgargs, res, str(exc))
                    ) from exc
            else:
                res_lgr(msg)

        ## output rendering
        if result_renderer is None or result_renderer == 'disabled':
            pass
        elif result_renderer == 'generic':
            last_result_reps, last_result, last_result_ts = \
                _render_result_generic(
                    res, render_n_repetitions,
                    last_result_reps, last_result, last_result_ts)
        elif result_renderer in ('json', 'json_pp'):
            _render_result_json(res, result_renderer.endswith('_pp'))
        elif result_renderer == 'tailored':
            cmd_class.custom_result_renderer(res, **allkwargs)
        elif hasattr(result_renderer, '__call__'):
            _render_result_customcall(res, result_renderer, allkwargs)
        else:
            raise ValueError(f'unknown result renderer "{result_renderer}"')

        ## error handling
        # looks for error status, and report at the end via
        # an exception
        if on_failure in ('continue', 'stop') \
                and res['status'] in ('impossible', 'error'):
            incomplete_results.append(res)
            if on_failure == 'stop':
                # first fail -> that's it
                # raise will happen after the loop
                break
        yield res
    # make sure to report on any issues that we had suppressed
    _display_suppressed_message(
        last_result_reps, render_n_repetitions, last_result_ts, final=True)


def _render_result_generic(
        res, render_n_repetitions,
        # status vars
        last_result_reps, last_result, last_result_ts):
    # which result dict keys to inspect for changes to discover repetitions
    # of similar messages
    repetition_keys = set(('action', 'status', 'type', 'refds'))

    trimmed_result = {k: v for k, v in res.items() if k in repetition_keys}
    if res.get('status', None) != 'notneeded' \
            and trimmed_result == last_result:
        # this is a similar report, suppress if too many, but count it
        last_result_reps += 1
        if last_result_reps < render_n_repetitions:
            generic_result_renderer(res)
        else:
            last_result_ts = _display_suppressed_message(
                last_result_reps, render_n_repetitions, last_result_ts)
    else:
        # this one is new, first report on any prev. suppressed results
        # by number, and then render this fresh one
        last_result_ts = _display_suppressed_message(
            last_result_reps, render_n_repetitions, last_result_ts,
            final=True)
        generic_result_renderer(res)
        last_result_reps = 0
    return last_result_reps, trimmed_result, last_result_ts


def _render_result_json(res, prettyprint):
    ui.message(json.dumps(
        {k: v for k, v in res.items()
         if k not in ('logger')},
        sort_keys=True,
        indent=2 if prettyprint else None,
        default=str))


def _render_result_customcall(res, result_renderer, allkwargs):
    try:
        result_renderer(res, **allkwargs)
    except Exception as e:
        lgr.warning('Result rendering failed for: %s [%s]',
                    res, CapturedException(e))


def keep_result(res, rfilter, **kwargs):
    if not rfilter:
        return True
    try:
        if not rfilter(res, **kwargs):
            # give the slightest indication which filter was employed
            raise ValueError(
                'excluded by filter {} with arguments {}'.format(rfilter, kwargs))
    except ValueError as e:
        # make sure to report the excluded result to massively improve
        # debugging experience
        lgr.debug('Not reporting result (%s): %s', CapturedException(e), res)
        return False
    return True


def xfm_result(res, xfm):
    if not xfm:
        return res

    return xfm(res)
