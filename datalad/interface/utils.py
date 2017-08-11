# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
import wrapt
import sys
import re
import shlex
from os import curdir
from os import pardir
from os import listdir
from os.path import join as opj
from os.path import lexists
from os.path import isdir
from os.path import dirname
from os.path import relpath
from os.path import sep
from os.path import split as psplit
from itertools import chain
from six import PY2

import json

# avoid import from API to not get into circular imports
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us
from datalad.utils import assure_list
from datalad.utils import get_dataset_root
from datalad.utils import unique
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.exceptions import IncompleteResultsError
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad import cfg as dlcfg
from datalad.dochelpers import exc_str


from datalad.support.constraints import Constraint

from datalad.ui import ui
import datalad.support.ansi_colors as ac

from datalad.interface.base import Interface
from datalad.interface.base import default_logchannels
from datalad.interface.base import get_allargs_as_kwargs
from datalad.interface.common_opts import eval_params
from datalad.interface.common_opts import eval_defaults
from .results import known_result_xfms


lgr = logging.getLogger('datalad.interface.utils')


def cls2cmdlinename(cls):
    "Return the cmdline command name from an Interface class"
    r = re.compile(r'([a-z0-9])([A-Z])')
    return r.sub('\\1-\\2', cls.__name__).lower()


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
        if not ds.repo or ds.repo.is_dirty(index=True,
                                           untracked_files=True,
                                           submodules=True):
            raise RuntimeError('dataset {} has unsaved changes'.format(ds))
    elif mode == 'save-before':
        if not ds.is_installed():
            raise RuntimeError('dataset {} is not yet installed'.format(ds))
        from datalad.interface.save import Save
        Save.__call__(dataset=ds, message=msg)
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


# TODO becomes obsolete with Interface._prep() gone
def get_paths_by_dataset(paths, recursive=False, recursion_limit=None,
                         out=None, dir_lookup=None, sub_paths=True):
    """Sort a list of paths per dataset they are contained in.

    Any paths that are not part of a dataset, or presently unavailable are
    reported.

    Parameter
    ---------
    paths : sequence
      A sequence of path specifications to sort.
    recursive : bool
      Flag whether to report subdatasets under any of the given paths
    recursion_limit :
      Depth constraint for recursion. See `subdatasets()` for more
      information.
    out : dict or None
      By default a new output dictionary is created, however an existing one
      can be provided via this argument to enable incremental processing.
    dir_lookup : dict or None, optional
      Optional lookup cache that maps paths to previously determined datasets.
      This can speed up repeated processing.
    sub_paths : bool, optional
      Provide a list containing the sub-dataset path, as the entry for that
      sub-dataset.  If False, empty list is assigned

    Returns
    -------
    Tuple(dict, list, list)
      Dict of `existing dataset path`: `path` mappings, the list of currently
      non-existing paths (possibly matching currently uninstalled datasets),
      and any paths that are not part of any dataset.
    """
    # sort paths into the respective datasets
    if dir_lookup is None:
        dir_lookup = {}
    if out is None:
        out = {}
    # paths that don't exist (yet)
    unavailable_paths = []
    nondataset_paths = []
    for path in unique(paths):
        if not lexists(path):
            # not there yet, impossible to say which ds it will actually
            # be in, if any
            unavailable_paths.append(path)
            continue
        # the path exists in some shape or form
        if isdir(path):
            # this could contain all types of additional content
            d = path
        else:
            # for everything else we are interested in the container
            d = dirname(path)
            if not d:
                d = curdir

        dspath = dir_lookup.get(d, None)
        if dspath:
            _ds_looked_up = True
        else:
            _ds_looked_up = False
            # this could be `None` if there is no git repo
            dspath = get_dataset_root(d)
            dir_lookup[d] = dspath

        if not dspath:
            nondataset_paths.append(path)
            continue

        if path in out.get(dspath, []):
            # we already recorded this path in the output
            # this can happen, whenever `path` is a subdataset, that was
            # discovered via recursive processing of another path before
            continue

        if isdir(path):
            ds = Dataset(dspath)
            # we need to doublecheck that this is not a subdataset mount
            # point, in which case get_dataset_root() would point to the parent.

            if not _ds_looked_up:
                # we didn't deal with it before

                # TODO this is a slow call, no need for dedicated RF, will vanish
                # together with the entire function
                smpath = ds.get_containing_subdataset(
                    path, recursion_limit=1).path
                if smpath != dspath:
                    # fix entry
                    dir_lookup[d] = smpath
                    # submodule still needs to be obtained
                    unavailable_paths.append(path)
                    continue
            else:
                # we figured out the dataset previously, so we can spare some
                # effort by not calling ds.subdatasets or
                # ds.get_containing_subdataset. Instead we just need
                # get_dataset_root, which is cheaper
                if dspath != get_dataset_root(dspath):
                    # if the looked up path isn't the default value,
                    # it's a 'fixed' entry for an unavailable dataset (see above)
                    unavailable_paths.append(path)
                    continue

            if recursive:
                # make sure we get everything relevant in all _checked out_
                # subdatasets, obtaining of previously unavailable subdataset
                # else done elsewhere
                for subdspath in ds.subdatasets(
                        fulfilled=True,
                        recursive=recursive,
                        recursion_limit=recursion_limit,
                        result_xfm='paths'):
                    if subdspath.startswith(_with_sep(path)):
                        # this subdatasets is underneath the search path
                        # be careful to not overwrite anything, in case
                        # this subdataset has been processed before
                        out[subdspath] = out.get(
                            subdspath,
                            [subdspath] if sub_paths else [])

        out[dspath] = out.get(dspath, []) + [path]
    return out, unavailable_paths, nondataset_paths


# TODO becomes obsolete with Interface._prep() gone
def get_normalized_path_arguments(paths, dataset=None, default=None):
    """Apply standard resolution to path arguments

    This is nothing more than a helper to standardize path argument
    preprocessing.

    Parameter
    ---------
    paths : sequence or single path
      Path(s) to normalize
    dataset : path or Dataset or None
      Optional dataset identifying something against which to resolve input
      path arguments
    default: sequence of paths or single path or None
      If `paths` is empty, use this instead

    Returns
    -------
    tuple(list(paths), path)
      Normalized paths and path to a potential dataset against which paths were
      resolved.
    """
    dataset_path = dataset.path if isinstance(dataset, Dataset) else dataset
    if not paths and default:
        paths = default
    paths = assure_list(paths)
    # resolve path(s):
    resolved_paths = [resolve_path(p, dataset) for p in paths]
    if dataset:
        # guarantee absolute paths
        resolved_paths = [opj(dataset_path, p) for p in resolved_paths]
    lgr.debug('Resolved input path arguments: %s', resolved_paths)
    return resolved_paths, dataset_path


def path_is_under(values, path=None):
    """Whether a given path is a subdirectory of any of the given test values

    Parameters
    ----------
    values : sequence or dict
      Paths to be tested against. This can be a dictionary in which case
      all values from all keys will be tested against.
    path : path or None
      Test path. If None is given, the process' working directory is
      used.

    Returns
    -------
    bool
    """
    if path is None:
        from datalad.utils import getpwd
        path = getpwd()
    if isinstance(values, dict):
        values = chain(*values.values())
    for p in values:
        rpath = relpath(p, start=path)
        if rpath == curdir \
                or rpath == pardir \
                or set(psplit(rpath)) == {pardir}:
            # first match is enough
            return True
    return False


def discover_dataset_trace_to_targets(basepath, targetpaths, current_trace, spec):
    """Discover the edges and nodes in a dataset tree to given target paths

    Parameters
    ----------
    basepath : path
      Path to a start or top-level dataset. Really has to be a path to a
      dataset!
    targetpaths : list(path)
      Any non-zero number of path that are termination points for the
      search algorithm. Can be paths to datasets, directories, or files
      (and any combination thereof).
    current_trace : list
      For a top-level call this should probably always be `[]`
    spec : dict
      `content_by_ds`-style dictionary that will receive information about the
      discovered datasets. Specifically, for each discovered dataset there
      will be in item with its path under the key (path) of the respective
      superdataset.

    Returns
    -------
    None
      Function calls itself recursively and populates `spec` in-place.
    """
    # this beast walks the directory tree from a given `basepath` until
    # it discovers any of the given `targetpaths`
    # if it finds one, it commits any accummulated trace of visited
    # datasets on this edge to the spec
    valid_repo = GitRepo.is_valid_repo(basepath)
    if valid_repo:
        # we are passing into a new dataset, extend the dataset trace
        current_trace = current_trace + [basepath]
    if basepath in targetpaths:
        # found a targetpath, commit the trace
        for i, p in enumerate(current_trace[:-1]):
            # TODO RF prepare proper annotated path dicts
            spec[p] = list(set(spec.get(p, []) + [current_trace[i + 1]]))
    if not isdir(basepath):
        # nothing underneath this one -> done
        return
    # this edge is not done, we need to try to reach any downstream
    # dataset
    for p in listdir(basepath):
        if valid_repo and p == '.git':
            # ignore gitdir to speed things up
            continue
        p = opj(basepath, p)
        if all(t != p and not t.startswith(_with_sep(p)) for t in targetpaths):
            # OPT listdir might be large and we could have only few items
            # in `targetpaths` -- so traverse only those in spec which have
            # leading dir basepath
            continue
        # we need to call this even for non-directories, to be able to match
        # file target paths
        discover_dataset_trace_to_targets(p, targetpaths, current_trace, spec)


def filter_unmodified(content_by_ds, refds, since):
    """Filter per-dataset path specifications based on modification history.

    This function takes a path specification dictionary, as produced by
    `Interface._prep()` and filters it such that only that subset of paths
    remains in the dictionary that corresponding to the set of changes in
    the given reference dataset since a given state.

    The change set is traced across all related subdatasets, i.e. if a submodule
    in the reference dataset is reported as modified then all paths for any given
    subdataset in the modified one are tested for changes too (based on the
    state at which the parent dataset reports a change in the subdataset), and so
    on.

    In doing so, not only unmodified given paths are removed, but also modified
    given paths are replaced by the set of actually modified paths within them.

    Only committed changes are considered!

    Parameters
    ----------
    content_by_ds : dict
      Per-dataset path specifications, as produced ,for example, by
      `Interface._prep()`
    refds : Dataset or *Repo or path
      Reference dataset for which to determine the initial change set
    since : state
      Any commit-ish/tree-ish supported by Git (tag, commit, branch, ...).
      Changes between this given state and the most recent commit are
      evaluated.

    Returns
    -------
    dict
      Filtered path spec dictionary. If `since` is not None, the output is
      guaranteed to only contain paths to modified, and presently existing
      components of subdatasets of the given reference dataset (and itself).
    """
    if since is None:
        # we want all, subds not matching the ref are assumed to have been
        # sorted out before (e.g. one level up)
        return content_by_ds
    # turn refds argument into a usable repo instance
    if not hasattr(refds, 'path'):
        # not a Repo or Dataset
        refds_path = refds
        refds = GitRepo(refds, create=False)
    else:
        refds_path = refds.path
    repo = refds.repo
    if hasattr(repo, 'repo'):
        # TODO use GitRepo.diff() when available (gh-1217)
        repo = repo.repo

    dict_class = content_by_ds.__class__    # could be ordered dict

    # life is simple: we diff the base dataset, and kill anything that
    # does not start with something that is in the diff
    # we cannot really limit the diff paths easily because we might get
    # or miss content (e.g. subdatasets) if we don't figure out which ones
    # are known -- and we don't want that
    try:
        diff = repo.commit().diff(since)
    except GitCommandError as exc:
        # could fail because `since` points to non existing location.
        # Unfortunately there might be no meaningful message
        # e.g. "fatal: ambiguous argument 'HEAD^': unknown revision or path not in the working tree"
        # logged within this GitCommandError for some reason! So let's check
        # that value of since post-error for being correct:
        try:
            refds.repo._git_custom_command(
                [],
                ['git', 'show', '--stat', since, '--'],
                expect_stderr=True, expect_fail=True)
            raise  # re-raise since our idea was incorrect
        except CommandError as ce_exc:
            if ce_exc.stderr.startswith('fatal: bad revision'):
                raise ValueError(
                    "Value since=%r is not valid. Git reports: %s" %
                    (since, exc_str(ce_exc))
                )
            else:
                raise  # re-raise

    # get all modified paths (with original? commit) that are still
    # present
    modified = dict((opj(refds_path, d.b_path),
                    d.b_blob.hexsha if d.b_blob else None)
                    for d in diff)
    if not modified:
        # nothing modified nothing to report
        return dict_class()
    # determine the subset that is a directory and hence is relevant for possible
    # subdatasets
    modified_dirs = {_with_sep(d) for d in modified if isdir(d)}
    # find the subdatasets matching modified paths, this will also kick out
    # any paths that are not in the dataset sub-hierarchy
    mod_subs = dict_class(
        (candds, paths)
        for candds, paths in content_by_ds.items()
        if candds != refds_path and
           any(_with_sep(candds).startswith(md) for md in modified_dirs)
    )
    # now query the next level down
    keep_subs = \
        [filter_unmodified(mod_subs, subds_path, modified[subds_path])
         for subds_path in mod_subs
         if subds_path in modified]
    # merge result list into a single dict
    keep = dict_class(
        (k, v) for d in keep_subs for k, v in d.items()
    )

    paths_refds = content_by_ds[refds_path]
    keep[refds_path] = [m for m in modified
                        if lexists(m)  # still around
                        and (m in paths_refds  # listed file, or subds
                        # or a modified path under a given directory
                        or any(m.startswith(_with_sep(p)) for p in paths_refds))]
    return keep


def eval_results(func):
    """Decorator for return value evaluation of datalad commands.

    Note, this decorator is only compatible with commands that return
    status dict sequences!

    Two basic modes of operation are supported: 1) "generator mode" that
    `yields` individual results, and 2) "list mode" that returns a sequence of
    results. The behavior can be selected via the kwarg `return_type`.
    Default is "list mode".

    This decorator implements common functionality for result rendering/output,
    error detection/handling, and logging.

    Result rendering/output can be triggered via the
    `datalad.api.result-renderer` configuration variable, or the
    `result_renderer` keyword argument of each decorated command. Supported
    modes are: 'default' (one line per result with action, status, path,
    and an optional message); 'json' (one object per result, like git-annex),
    'json_pp' (like 'json', but pretty-printed spanning multiple lines),
    'tailored' custom output formatting provided by each command
    class (if any).

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

    @wrapt.decorator
    def eval_func(wrapped, instance, args, kwargs):
        # for result filters and pre/post plugins
        # we need to produce a dict with argname/argvalue pairs for all args
        # incl. defaults and args given as positionals
        allkwargs = get_allargs_as_kwargs(wrapped, args, kwargs)
        # determine class, the __call__ method of which we are decorating:
        # Ben: Note, that this is a bit dirty in PY2 and imposes restrictions on
        # when and how to use eval_results as well as on how to name a command's
        # module and class. As of now, we are inline with these requirements as
        # far as I'm aware.
        mod = sys.modules[wrapped.__module__]
        if PY2:
            # we rely on:
            # - decorated function is method of a subclass of Interface
            # - the name of the class matches the last part of the module's name
            #   if converted to lower
            # for example:
            # ..../where/ever/mycommand.py:
            # class MyCommand(Interface):
            #     @eval_results
            #     def __call__(..)
            command_class_names = \
                [i for i in mod.__dict__
                 if type(mod.__dict__[i]) == type and
                 issubclass(mod.__dict__[i], Interface) and
                 i.lower() == wrapped.__module__.split('.')[-1].replace('_', '')]
            assert(len(command_class_names) == 1)
            command_class_name = command_class_names[0]
        else:
            command_class_name = wrapped.__qualname__.split('.')[-2]
        _func_class = mod.__dict__[command_class_name]
        lgr.debug("Determined class of decorated function: %s", _func_class)

        # retrieve common options from kwargs, and fall back on the command
        # class attributes, or general defaults if needed
        common_params = {
            p_name: kwargs.pop(
                p_name,
                getattr(_func_class, p_name, eval_defaults[p_name]))
            for p_name in eval_params}
        # short cuts and configured setup for common options
        on_failure = common_params['on_failure']
        return_type = common_params['return_type']
        # resolve string labels for transformers too
        result_xfm = common_params['result_xfm']
        if result_xfm in known_result_xfms:
            result_xfm = known_result_xfms[result_xfm]
        result_renderer = common_params['result_renderer']
        # TODO remove this conditional branch entirely, done outside
        if not result_renderer:
            result_renderer = dlcfg.get('datalad.api.result-renderer', None)
        # wrap the filter into a helper to be able to pass additional arguments
        # if the filter supports it, but at the same time keep the required interface
        # as minimal as possible. Also do this here, in order to avoid this test
        # to be performed for each return value
        result_filter = common_params['result_filter']
        _result_filter = result_filter
        if result_filter:
            if isinstance(result_filter, Constraint):
                _result_filter = result_filter.__call__
            if (PY2 and inspect.getargspec(_result_filter).keywords) or \
                    (not PY2 and inspect.getfullargspec(_result_filter).varkw):

                def _result_filter(res):
                    return result_filter(res, **allkwargs)

        def _get_plugin_specs(param_key=None, cfg_key=None):
            spec = common_params.get(param_key, None)
            if spec is not None:
                # this is already a list of lists
                return spec

            spec = dlcfg.get(cfg_key, None)
            if spec is None:
                return
            elif not isinstance(spec, tuple):
                spec = [spec]
            return [shlex.split(s) for s in spec]

        # query cfg for defaults
        cmdline_name = cls2cmdlinename(_func_class)
        run_before = _get_plugin_specs(
            'run_before',
            'datalad.{}.run-before'.format(cmdline_name))
        run_after = _get_plugin_specs(
            'run_after',
            'datalad.{}.run-after'.format(cmdline_name))

        # this internal helper function actually drives the command
        # generator-style, it may generate an exception if desired,
        # on incomplete results
        def generator_func(*_args, **_kwargs):
            from datalad.plugin import Plugin

            # flag whether to raise an exception
            incomplete_results = []
            # track what actions were performed how many times
            action_summary = {}

            for pluginspec in run_before or []:
                lgr.debug('Running pre-proc plugin %s', pluginspec)
                for r in _process_results(
                        Plugin.__call__(
                            pluginspec,
                            dataset=allkwargs.get('dataset', None),
                            return_type='generator'),
                        _func_class, action_summary,
                        on_failure, incomplete_results,
                        result_renderer, result_xfm, result_filter,
                        **_kwargs):
                    yield r

            # process main results
            for r in _process_results(
                    wrapped(*_args, **_kwargs),
                    _func_class, action_summary,
                    on_failure, incomplete_results,
                    result_renderer, result_xfm, _result_filter, **_kwargs):
                yield r

            for pluginspec in run_after or []:
                lgr.debug('Running post-proc plugin %s', pluginspec)
                for r in _process_results(
                        Plugin.__call__(
                            pluginspec,
                            dataset=allkwargs.get('dataset', None),
                            return_type='generator'),
                        _func_class, action_summary,
                        on_failure, incomplete_results,
                        result_renderer, result_xfm, result_filter,
                        **_kwargs):
                    yield r

            # result summary before a potential exception
            if result_renderer == 'default' and action_summary and \
                    sum(sum(s.values()) for s in action_summary.values()) > 1:
                # give a summary in default mode, when there was more than one
                # action performed
                ui.message("action summary:\n  {}".format(
                    '\n  '.join('{} ({})'.format(
                        act,
                        ', '.join('{}: {}'.format(status, action_summary[act][status])
                                  for status in sorted(action_summary[act])))
                                for act in sorted(action_summary))))

            if incomplete_results:
                raise IncompleteResultsError(
                    failed=incomplete_results,
                    msg="Command did not complete successfully")

        if return_type == 'generator':
            # hand over the generator
            return generator_func(*args, **kwargs)
        else:
            @wrapt.decorator
            def return_func(wrapped_, instance_, args_, kwargs_):
                results = wrapped_(*args_, **kwargs_)
                if inspect.isgenerator(results):
                    # unwind generator if there is one, this actually runs
                    # any processing
                    results = list(results)
                # render summaries
                if not result_xfm and result_renderer == 'tailored':
                    # cannot render transformed results
                    if hasattr(_func_class, 'custom_result_summary_renderer'):
                        _func_class.custom_result_summary_renderer(results)
                if return_type == 'item-or-list' and \
                        len(results) < 2:
                    return results[0] if results else None
                else:
                    return results

            return return_func(generator_func)(*args, **kwargs)

    return eval_func(func)


def _process_results(
        results, cmd_class,
        action_summary, on_failure, incomplete_results,
        result_renderer, result_xfm, result_filter, **kwargs):
    # private helper pf @eval_results
    # loop over results generated from some source and handle each
    # of them according to the requested behavior (logging, rendering, ...)
    for res in results:
        actsum = action_summary.get(res['action'], {})
        if res['status']:
            actsum[res['status']] = actsum.get(res['status'], 0) + 1
            action_summary[res['action']] = actsum
        ## log message, if a logger was given
        # remove logger instance from results, as it is no longer useful
        # after logging was done, it isn't serializable, and generally
        # pollutes the output
        res_lgr = res.pop('logger', None)
        if isinstance(res_lgr, logging.Logger):
            # didn't get a particular log function, go with default
            res_lgr = getattr(res_lgr, default_logchannels[res['status']])
        if res_lgr and 'message' in res:
            msg = res['message']
            msgargs = None
            if isinstance(msg, tuple):
                msgargs = msg[1:]
                msg = msg[0]
            if 'path' in res:
                msg = '{} [{}({})]'.format(
                    msg, res['action'], res['path'])
            if msgargs:
                # support string expansion of logging to avoid runtime cost
                res_lgr(msg, *msgargs)
            else:
                res_lgr(msg)
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
        if result_filter:
            try:
                if not result_filter(res):
                    raise ValueError('excluded by filter')
            except ValueError as e:
                lgr.debug('not reporting result (%s)', exc_str(e))
                continue
        ## output rendering
        # TODO RF this in a simple callable that gets passed into this function
        if result_renderer == 'default':
            # TODO have a helper that can expand a result message
            ui.message('{action}({status}): {path}{type}{msg}'.format(
                action=ac.color_word(res['action'], ac.BOLD),
                status=ac.color_status(res['status']),
                path=relpath(res['path'],
                             res['refds']) if res.get('refds', None) else res['path'],
                type=' ({})'.format(
                    ac.color_word(res['type'], ac.MAGENTA)
                    ) if 'type' in res else '',
                msg=' [{}]'.format(
                    res['message'][0] % res['message'][1:]
                    if isinstance(res['message'], tuple) else res['message'])
                if 'message' in res else ''))
        elif result_renderer in ('json', 'json_pp'):
            ui.message(json.dumps(
                {k: v for k, v in res.items()
                 if k not in ('message', 'logger')},
                sort_keys=True,
                indent=2 if result_renderer.endswith('_pp') else None))
        elif result_renderer == 'tailored':
            if hasattr(cmd_class, 'custom_result_renderer'):
                cmd_class.custom_result_renderer(res, **kwargs)
        elif hasattr(result_renderer, '__call__'):
            result_renderer(res, **kwargs)
        if result_xfm:
            res = result_xfm(res)
            if res is None:
                continue
        yield res
