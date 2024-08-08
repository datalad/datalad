# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utility functions for result hooks

"""

__docformat__ = 'restructuredtext'

import json
import logging

from datalad.support.exceptions import CapturedException

lgr = logging.getLogger('datalad.core.local.resulthooks')


def get_jsonhooks_from_config(cfg):
    """Parse out hook definitions given a ConfigManager instance

    Returns
    -------
    dict
      where keys are hook names/labels, and each value is a dict with
      three keys: 'cmd' contains the name of the to-be-executed DataLad
      command; 'args' has a JSON-encoded string with a dict of keyword
      arguments for the command (format()-language based placeholders
      can be present); 'match' holds a JSON-encoded string representing
      a dict with key/value pairs that need to match a result in order
      for a hook to be triggered.
    """
    hooks = {}
    for h in cfg.keys():
        if not (h.startswith('datalad.result-hook.') and h.endswith('.match-json')):
            continue
        hook_basevar = h[:-11]
        hook_name = hook_basevar[20:]
        # do not use a normal `get()` here, because it reads the committed dataset
        # config too. That means a datalad update can silently bring in new
        # procedure definitions from the outside, and in some sense enable
        # remote code execution by a 3rd-party
        call = cfg.get_from_source(
            'local',
            '{}.call-json'.format(hook_basevar),
            None
        )
        if not call:
            lgr.warning(
                'Incomplete result hook configuration %s in %s',
                hook_basevar, cfg)
            continue
        # split command from any args
        call = call.split(maxsplit=1)
        # get the match specification in JSON format
        try:
            match = json.loads(cfg.get(h))
        except Exception as e:
            ce = CapturedException(e)
            lgr.warning(
                'Invalid match specification in %s: %s [%s], '
                'hook will be skipped',
                h, cfg.get(h), ce)
            continue

        hooks[hook_name] = dict(
            cmd=call[0],
            # support no-arg calls too
            args=call[1] if len(call) > 1 else '{{}}',
            match=match,
        )
    return hooks


def match_jsonhook2result(hook, res, match):
    """Evaluate a hook's result match definition against a concrete result

    A match definition is a dict that can contain any number of keys. For each
    key it is tested, if the value matches the one in a given result.
    If all present key/value pairs match, the hook is executed. In addition to
    ``==`` tests, ``in``, ``not in``, and ``!=`` tests are supported. The
    test operation can be given by wrapping the test value into a list, the
    first item is the operation label 'eq', 'neq', 'in', 'nin'; the second value
    is the test value (set). Example::

        {
          "type": ["in", ["file", "directory"]],
          "action": "get",
          "status": "notneeded"
        }

    If a to be tested value is a list, an 'eq' operation needs to be specified
    explicitly in order to disambiguate the definition.

    Parameters
    ----------
    hook : str
      Name of the hook
    res : dict
      Result dictionary
    match : dict
      Match definition (see above for details).

    Returns
    -------
    bool
      True if the given result matches the hook's match definition, or
      False otherwise.
    """
    for k, v in match.items():
        # do not test 'k not in res', because we could have a match that
        # wants to make sure that a particular value is not present, and
        # not having the key would be OK in that case

        # in case the target value is an actual list, an explicit action 'eq'
        # must be given
        action, val = (v[0], v[1]) if isinstance(v, list) else ('eq', v)
        if action == 'eq':
            if k in res and res[k] == val:
                continue
        elif action == 'neq':
            if k not in res or res[k] != val:
                continue
        elif action == 'in':
            if k in res and res[k] in val:
                continue
        elif action == 'nin':
            if k not in res or res[k] not in val:
                continue
        else:
            lgr.warning(
                'Unknown result comparison operation %s for hook %s, skipped',
                action, hook)
        # indentation level is intended!
        return False
    return True


def run_jsonhook(hook, spec, res, dsarg=None):
    """Execute a hook on a given result

    A hook definition's 'call' specification may contain placeholders that
    will be expanded using matching values in the given result record. In
    addition to keys in the result a '{dsarg}' placeholder is supported.
    The characters '{' and '}' in the 'call' specification that are not part
    of format() placeholders have to be escaped as '{{' and '}}'. Example
    'call' specification to execute the DataLad ``unlock`` command::

        unlock {{"dataset": "{dsarg}", "path": "{path}"}}

    Parameters
    ----------
    hook : str
      Name of the hook
    spec : dict
      Hook definition as returned by `get_hooks_from_config()`
    res : dict
      Result records that were found to match the hook definition.
    dsarg : Dataset or str or None, optional
      Value to substitute a {dsarg} placeholder in a hook 'call' specification
      with. Non-string values are automatically converted.

    Yields
    ------
    dict
      Any result yielded by the command executed as hook.
    """
    import datalad.api as dl
    cmd_name = spec['cmd']
    if not hasattr(dl, cmd_name):
        # TODO maybe a proper error result?
        lgr.warning(
            'Hook %s requires unknown command %s, skipped',
            hook, cmd_name)
        return
    cmd = getattr(dl, cmd_name)
    # apply potential substitutions on the string form of the args
    # for this particular result
    # take care of proper JSON encoding for each value
    enc = json.JSONEncoder().encode
    # we have to ensure JSON encoding of all values (some might be Path instances),
    # we are taking off the outer quoting, to enable flexible combination
    # of individual items in supplied command and argument templates
    args = spec['args'].format(
        # we cannot use a dataset instance directly but must take the
        # detour over the path location in order to have string substitution
        # be possible
        dsarg='' if dsarg is None else enc(dsarg.path).strip('"')
        if isinstance(dsarg, dl.Dataset) else enc(dsarg).strip('"'),
        # skip any present logger that we only carry for internal purposes
        **{k: enc(str(v)).strip('"') for k, v in res.items() if k != 'logger'})
    # now load
    try:
        args = json.loads(args)
    except Exception as e:
        ce = CapturedException(e)
        lgr.warning(
            'Invalid argument specification for hook %s '
            '(after parameter substitutions): %s [%s], '
            'hook will be skipped',
            hook, args, ce)
        return
    # only debug level, the hook can issue its own results and communicate
    # through them
    lgr.debug('Running hook %s: %s%s', hook, cmd_name, args)
    for r in cmd(**args):
        yield r
