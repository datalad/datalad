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
from os import curdir
from os import pardir
from os import listdir
from os import linesep
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
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureCallable
from datalad.support.param import Parameter

from datalad.ui import ui

from .base import Interface
from .base import update_docstring_with_parameters
from .base import alter_interface_docs_for_api
from .base import merge_allargs2kwargs
from .results import known_result_xfms


lgr = logging.getLogger('datalad.interface.utils')


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


# define parameters to be used by eval_results to tune behavior
# Note: This is done outside eval_results in order to be available when building
# docstrings for the decorated functions
# TODO: May be we want to move them to be part of the classes _params. Depends
# on when and how eval_results actually has to determine the class.
# Alternatively build a callable class with these to even have a fake signature
# that matches the parameters, so they can be evaluated and defined the exact
# same way.

eval_params = dict(
    return_type=Parameter(
        doc="""return value behavior switch. If 'item-or-list' a single
        value is returned instead of a one-item return value list, or a
        list in case of multiple return values. `None` is return in case
        of an empty list.""",
        constraints=EnsureChoice('generator', 'list', 'item-or-list')),
    result_filter=Parameter(
        doc="""if given, each to-be-returned
        status dictionary is passed to this callable, and is only
        returned if the callable's return value does not
        evaluate to False or a ValueError exception is raised. If the given
        callable supports `**kwargs` it will additionally be passed the
        keyword arguments of the original API call.""",
        constraints=EnsureCallable() | EnsureNone()),
    result_xfm=Parameter(
        doc="""if given, each to-be-returned result
        status dictionary is passed to this callable, and its return value
        becomes the result instead. This is different from
        `result_filter`, as it can perform arbitrary transformation of the
        result value. This is mostly useful for top-level command invocations
        that need to provide the results in a particular format. Instead of
        a callable, a label for a pre-crafted result transformation can be
        given.""",
        constraints=EnsureChoice(*list(known_result_xfms.keys())) | EnsureCallable() | EnsureNone()),
    result_renderer=Parameter(
        doc="""format of return value rendering on stdout""",
        constraints=EnsureChoice('default', 'json', 'json_pp', 'tailored') | EnsureNone()),
    on_failure=Parameter(
        doc="""behavior to perform on failure: 'ignore' any failure is reported,
        but does not cause an exception; 'continue' if any failure occurs an
        exception will be raised at the end, but processing other actions will
        continue for as long as possible; 'stop': processing will stop on first
        failure and an exception is raised. A failure is any result with status
        'impossible' or 'error'. Raised exception is an IncompleteResultsError
        that carries the result dictionaries of the failures in its `failed`
        attribute.""",
        constraints=EnsureChoice('ignore', 'continue', 'stop')),
)
eval_defaults = dict(
    return_type='list',
    result_filter=None,
    result_renderer=None,
    result_xfm=None,
    on_failure='continue',
)


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

    default_logchannels = {
        '': 'debug',
        'ok': 'debug',
        'notneeded': 'debug',
        'impossible': 'warning',
        'error': 'error',
    }

    @wrapt.decorator
    def eval_func(wrapped, instance, args, kwargs):

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

        common_params = {
            p_name: kwargs.pop(
                p_name,
                getattr(_func_class, p_name, eval_defaults[p_name]))
            for p_name in eval_params}
        result_renderer = common_params['result_renderer']

        def generator_func(*_args, **_kwargs):
            # obtain results
            results = wrapped(*_args, **_kwargs)
            # flag whether to raise an exception
            # TODO actually compose a meaningful exception
            incomplete_results = []
            # inspect and render
            result_filter = common_params['result_filter']
            # wrap the filter into a helper to be able to pass additional arguments
            # if the filter supports it, but at the same time keep the required interface
            # as minimal as possible. Also do this here, in order to avoid this test
            # to be performed for each return value
            _result_filter = result_filter
            if result_filter:
                if isinstance(result_filter, Constraint):
                    _result_filter = result_filter.__call__
                if (PY2 and inspect.getargspec(_result_filter).keywords) or \
                        (not PY2 and inspect.getfullargspec(_result_filter).varkw):
                    # we need to produce a dict with argname/argvalue pairs for all args
                    # incl. defaults and args given as positionals
                    fullkwargs_ = merge_allargs2kwargs(wrapped, _args, _kwargs)

                    def _result_filter(res):
                        return result_filter(res, **fullkwargs_)
            result_renderer = common_params['result_renderer']
            result_xfm = common_params['result_xfm']
            if result_xfm in known_result_xfms:
                result_xfm = known_result_xfms[result_xfm]
            on_failure = common_params['on_failure']
            if not result_renderer:
                result_renderer = dlcfg.get('datalad.api.result-renderer', None)
            # track what actions were performed how many times
            action_summary = {}
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
                if _result_filter:
                    try:
                        if not _result_filter(res):
                            raise ValueError('excluded by filter')
                    except ValueError as e:
                        lgr.debug('not reporting result (%s)', exc_str(e))
                        continue
                ## output rendering
                if result_renderer == 'default':
                    # TODO have a helper that can expand a result message
                    ui.message('{action}({status}): {path}{type}{msg}'.format(
                        action=res['action'],
                        status=res['status'],
                        path=relpath(res['path'],
                                     res['refds']) if res.get('refds', None) else res['path'],
                        type=' ({})'.format(res['type']) if 'type' in res else '',
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
                    if hasattr(_func_class, 'custom_result_renderer'):
                        _func_class.custom_result_renderer(res, **_kwargs)
                elif hasattr(result_renderer, '__call__'):
                    result_renderer(res, **_kwargs)
                if result_xfm:
                    res = result_xfm(res)
                    if res is None:
                        continue
                yield res

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
                # stupid catch all message <- tailor TODO
                raise IncompleteResultsError(
                    failed=incomplete_results,
                    msg="Command did not complete successfully")

        if common_params['return_type'] == 'generator':
            return generator_func(*args, **kwargs)
        else:
            @wrapt.decorator
            def return_func(wrapped_, instance_, args_, kwargs_):
                results = wrapped_(*args_, **kwargs_)
                if inspect.isgenerator(results):
                    results = list(results)
                # render summaries
                if not common_params['result_xfm'] and result_renderer == 'tailored':
                    # cannot render transformed results
                    if hasattr(_func_class, 'custom_result_summary_renderer'):
                        _func_class.custom_result_summary_renderer(results)
                if common_params['return_type'] == 'item-or-list' and \
                        len(results) < 2:
                    return results[0] if results else None
                else:
                    return results

            return return_func(generator_func)(*args, **kwargs)

    return eval_func(func)


def build_doc(cls, **kwargs):
    """Decorator to build docstrings for datalad commands

    It's intended to decorate the class, the __call__-method of which is the
    actual command. It expects that __call__-method to be decorated by
    eval_results.

    Parameters
    ----------
    cls: Interface
      class defining a datalad command
    """

    # Note, that this is a class decorator, which is executed only once when the
    # class is imported. It builds the docstring for the class' __call__ method
    # and returns the original class.
    #
    # This is because a decorator for the actual function would not be able to
    # behave like this. To build the docstring we need to access the attribute
    # _params of the class. From within a function decorator we cannot do this
    # during import time, since the class is being built in this very moment and
    # is not yet available in the module. And if we do it from within the part
    # of a function decorator, that is executed when the function is called, we
    # would need to actually call the command once in order to build this
    # docstring.

    lgr.debug("Building doc for {}".format(cls))

    cls_doc = cls.__doc__
    if hasattr(cls, '_docs_'):
        # expand docs
        cls_doc = cls_doc.format(**cls._docs_)

    call_doc = None
    # suffix for update_docstring_with_parameters:
    if cls.__call__.__doc__:
        call_doc = cls.__call__.__doc__

    # build standard doc and insert eval_doc
    spec = getattr(cls, '_params_', dict())
    # get docs for eval_results parameters:
    spec.update(eval_params)

    update_docstring_with_parameters(
        cls.__call__, spec,
        prefix=alter_interface_docs_for_api(cls_doc),
        suffix=alter_interface_docs_for_api(call_doc),
        add_args=eval_defaults if not hasattr(cls, '_no_eval_results') else None
    )

    # return original
    return cls
