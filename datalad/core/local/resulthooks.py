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

import logging
import json

lgr = logging.getLogger('datalad.core.local.hooks')


def get_hooks_from_config(cfg):
    hooks = {}
    for h in (k for k in cfg.keys()
              if k.startswith('datalad.result-hook.')
              and k.endswith('.match')):
        proc = cfg.get('{}.proc'.format(h[:-6]), None)
        if not proc:
            lgr.warning(
                'Incomplete result hook configuration %s in %s' % (
                    h[:-6], cfg))
            continue
        sep = proc.index(' ')
        hooks[h[20:-6]] = dict(
            cmd=proc[:sep],
            args=proc[sep + 1:],
            match=json.loads(cfg.get(h)),
        )
    return hooks


def match_hook2result(hook, res, match):
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


def run_hook(hook, spec, r, dataset_arg):
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
        dsarg='' if dataset_arg is None else enc(dataset_arg.path).strip('"')
        if isinstance(dataset_arg, dl.Dataset) else enc(dataset_arg).strip('"'),
        # skip any present logger that we only carry for internal purposes
        **{k: enc(str(v)).strip('"') for k, v in r.items() if k != 'logger'})
    # now load
    args = json.loads(args)
    # only debug level, the hook can issue its own results and communicate
    # through them
    lgr.debug('Running hook %s: %s%s', hook, cmd_name, args)
    for r in cmd(**args):
        yield r
