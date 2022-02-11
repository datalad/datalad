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

import inspect
import logging
import sys
from functools import wraps
from time import time
from os import listdir
from os.path import join as opj
from os.path import isdir
from os.path import relpath
from os.path import sep

import json

# avoid import from API to not get into circular imports
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import (
    path_startswith,
    path_is_subpath,
    ensure_unicode,
    getargspec,
    get_wrapped_class,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import (
    CapturedException,
    IncompleteResultsError,
)
from datalad import cfg as dlcfg
from datalad.dochelpers import single_or_plural

from datalad.ui import ui
import datalad.support.ansi_colors as ac

from datalad.interface.base import default_logchannels
from datalad.interface.base import get_allargs_as_kwargs
from datalad.interface.common_opts import eval_params
from .results import known_result_xfms
from datalad.core.local.resulthooks import (
    get_jsonhooks_from_config,
    match_jsonhook2result,
    run_jsonhook,
)

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
    # if it finds one, it commits any accummulated trace of visited
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
    """Decorator for return value evaluation of datalad commands.

    Note, this decorator is only compatible with commands that return
    status dict sequences!

    Two basic modes of operation are supported: 1) "generator mode" that
    `yields` individual results, and 2) "list mode" that returns a sequence of
    results. The behavior can be selected via the kwarg `return_type`.
    Default is "list mode".

    This decorator implements common functionality for result rendering/output,
    error detection/handling, and logging.

    Result rendering/output configured via the `result_renderer` keyword
    argument of each decorated command. Supported modes are: 'generic' (a
    generic renderer producing one line per result with key info like action,
    status, path, and an optional message); 'json' (a complete JSON line
    serialization of the full result record), 'json_pp' (like 'json', but
    pretty-printed spanning multiple lines), 'tailored' custom output
    formatting provided by each command class (if any), or 'disabled' for
    no result rendering.

    Error detection works by inspecting the `status` item of all result
    dictionaries. Any occurrence of a status other than 'ok' or 'notneeded'
    will cause an IncompleteResultsError exception to be raised that carries
    the failed actions' status dictionaries in its `failed` attribute.

    Status messages will be logged automatically, by default the following
    association of result status and log channel will be used: 'ok' (debug),
    'notneeded' (debug), 'impossible' (warning), 'error' (error).  Logger
    instances included in the results are used to capture the origin of a
    status report.

    Parameters
    ----------
    func: function
      __call__ method of a subclass of Interface,
      i.e. a datalad command definition
    """

    @wraps(wrapped)
    def eval_func(*args, **kwargs):
        lgr.log(2, "Entered eval_func for %s", wrapped)
        # determine the command class associated with `wrapped`
        wrapped_class = get_wrapped_class(wrapped)

        # retrieve common options from kwargs, and fall back on the command
        # class attributes, or general defaults if needed
        kwargs = kwargs.copy()  # we will pop, which might cause side-effect
        common_params = {
            p_name: kwargs.pop(
                # go with any explicitly given default
                p_name,
                # otherwise determine the command class and pull any
                # default set in that class
                getattr(wrapped_class, p_name))
            for p_name in eval_params}

        # for result filters
        # we need to produce a dict with argname/argvalue pairs for all args
        # incl. defaults and args given as positionals
        allkwargs = get_allargs_as_kwargs(wrapped, args,
                                          {**kwargs, **common_params})

        # short cuts and configured setup for common options
        return_type = common_params['return_type']
        result_filter = get_result_filter(common_params['result_filter'])
        # resolve string labels for transformers too
        result_xfm = known_result_xfms.get(
            common_params['result_xfm'],
            # use verbatim, if not a known label
            common_params['result_xfm'])
        result_renderer = common_params['result_renderer']

        if result_renderer == 'tailored' and not hasattr(wrapped_class,
                                                         'custom_result_renderer'):
            # a tailored result renderer is requested, but the class
            # does not provide any, fall back to the generic one
            result_renderer = 'generic'
        if result_renderer == 'default':
            # standardize on the new name 'generic' to avoid more complex
            # checking below
            result_renderer = 'generic'
        # look for potential override of logging behavior
        result_log_level = dlcfg.get('datalad.log.result-level', 'debug')

        # query cfg for defaults
        # .is_installed and .config can be costly, so ensure we do
        # it only once. See https://github.com/datalad/datalad/issues/3575
        dataset_arg = allkwargs.get('dataset', None)
        ds = None
        if dataset_arg is not None:
            from datalad.distribution.dataset import Dataset
            if isinstance(dataset_arg, Dataset):
                ds = dataset_arg
            else:
                try:
                    ds = Dataset(dataset_arg)
                except ValueError:
                    pass

        # look for hooks
        hooks = get_jsonhooks_from_config(ds.config if ds else dlcfg)

        # this internal helper function actually drives the command
        # generator-style, it may generate an exception if desired,
        # on incomplete results
        def generator_func(*_args, **_kwargs):
            # flag whether to raise an exception
            incomplete_results = []
            # track what actions were performed how many times
            action_summary = {}

            # if a custom summary is to be provided, collect the results
            # of the command execution
            results = []
            do_custom_result_summary = result_renderer in (
                'tailored', 'generic', 'default') and hasattr(
                    wrapped_class,
                    'custom_result_summary_renderer')
            pass_summary = do_custom_result_summary \
                and getattr(wrapped_class,
                            'custom_result_summary_renderer_pass_summary',
                            None)

            # process main results
            for r in _process_results(
                    # execution
                    wrapped(*_args, **_kwargs),
                    wrapped_class,
                    common_params['on_failure'],
                    # bookkeeping
                    action_summary,
                    incomplete_results,
                    # communication
                    result_renderer,
                    result_log_level,
                    # let renderers get to see how a command was called
                    allkwargs):
                for hook, spec in hooks.items():
                    # run the hooks before we yield the result
                    # this ensures that they are executed before
                    # a potentially wrapper command gets to act
                    # on them
                    if match_jsonhook2result(hook, r, spec['match']):
                        lgr.debug('Result %s matches hook %s', r, hook)
                        # a hook is also a command that yields results
                        # so yield them outside too
                        # users need to pay attention to void infinite
                        # loops, i.e. when a hook yields a result that
                        # triggers that same hook again
                        for hr in run_jsonhook(hook, spec, r, dataset_arg):
                            # apply same logic as for main results, otherwise
                            # any filters would only tackle the primary results
                            # and a mixture of return values could happen
                            if not keep_result(hr, result_filter, **allkwargs):
                                continue
                            hr = xfm_result(hr, result_xfm)
                            # rationale for conditional is a few lines down
                            if hr:
                                yield hr
                if not keep_result(r, result_filter, **allkwargs):
                    continue
                r = xfm_result(r, result_xfm)
                # in case the result_xfm decided to not give us anything
                # exclude it from the results. There is no particular reason
                # to do so other than that it was established behavior when
                # this comment was written. This will not affect any real
                # result record
                if r:
                    yield r

                # collect if summary is desired
                if do_custom_result_summary:
                    results.append(r)

            # result summary before a potential exception
            # custom first
            if do_custom_result_summary:
                if pass_summary:
                    summary_args = (results, action_summary)
                else:
                    summary_args = (results,)
                wrapped_class.custom_result_summary_renderer(*summary_args)
            elif result_renderer in ('generic', 'default') \
                    and action_summary \
                    and sum(sum(s.values())
                            for s in action_summary.values()) > 1:
                # give a summary in generic mode, when there was more than one
                # action performed
                render_action_summary(action_summary)

            if incomplete_results:
                raise IncompleteResultsError(
                    failed=incomplete_results,
                    msg="Command did not complete successfully")

        if return_type == 'generator':
            # hand over the generator
            lgr.log(2, "Returning generator_func from eval_func for %s", wrapped_class)
            return generator_func(*args, **kwargs)
        else:
            @wraps(generator_func)
            def return_func(*args_, **kwargs_):
                results = generator_func(*args_, **kwargs_)
                if inspect.isgenerator(results):
                    # unwind generator if there is one, this actually runs
                    # any processing
                    results = list(results)
                if return_type == 'item-or-list' and \
                        len(results) < 2:
                    return results[0] if results else None
                else:
                    return results

            lgr.log(2, "Returning return_func from eval_func for %s", wrapped_class)
            return return_func(*args, **kwargs)

    ret = eval_func
    ret._eval_results = True
    return ret


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
