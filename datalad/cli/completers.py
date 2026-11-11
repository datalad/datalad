# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Shell completion of parameter values

A :class:`~datalad.support.param.Parameter` declares how its values are to be
completed via its ``completer``: either the name of one of the `completers`
below, or a list of values to choose from, or a callable following the
argcomplete completer protocol, i.e. accepting ``prefix``, ``action``,
``parser``, and ``parsed_args`` keyword arguments and returning an iterable of
candidate values, or a mapping of candidate values to their descriptions
(shown by e.g. zsh and fish).
Without a ``completer`` one could still be derived from the ``constraints``
of the parameter, see `get_param_completer`.

The CLI parser attaches completers to the respective ``argparse`` actions,
but only when invoked by argcomplete: this module is not imported otherwise.
But then it is on every <TAB> press, so it must stay fast to import, and
completers must be fast to run.
"""

__docformat__ = 'restructuredtext'

import logging
import os
from functools import wraps

from datalad.distribution.dataset import (
    EnsureDataset,
    require_dataset,
)
from datalad.support.constraints import (
    AltConstraints,
    EnsureChoice,
)
from datalad.support.exceptions import (
    CapturedException,
    NoDatasetFound,
)
from datalad.utils import (
    chpwd,
    getpwd,
)

lgr = logging.getLogger('datalad.cli.completers')


def _get_pwd(parsed_args):
    """Return the directory a command would run in

    ``-C`` is only acted upon after argument parsing, i.e. not yet when
    completing, but relative paths (e.g. of ``-d``) must be interpreted
    relative to it.
    """
    path = getpwd()
    for p in getattr(parsed_args, 'change_path', None) or []:
        path = os.path.join(path, os.path.expanduser(p))
    return path


def _get_dataset(parsed_args):
    """Return the dataset a command would operate on, or None if there is none

    Honors any ``-C`` and ``-d/--dataset`` already given on the command line
    preceding the word to be completed.
    """
    with chpwd(_get_pwd(parsed_args)):
        try:
            return require_dataset(
                getattr(parsed_args, 'dataset', None),
                check_installed=True,
                purpose='shell completion')
        except NoDatasetFound as e:
            lgr.debug("No dataset to complete for: %s", CapturedException(e))
            return None


def _startingwith(prefix, values):
    return sorted(v for v in set(values) if v.startswith(prefix))


def complete_siblings(prefix, parsed_args=None, **kwargs):
    """Names of the siblings of the dataset, described by their URLs"""
    ds = _get_dataset(parsed_args)
    if ds is None:
        return {}
    repo = ds.repo
    return {
        name: repo.config.get(f'remote.{name}.url', '')
        for name in _startingwith(prefix, repo.get_remotes())
    }


def complete_revisions(prefix, parsed_args=None, **kwargs):
    """Names of the branches, remote branches, and tags of the dataset

    But for the ``git-annex`` branches, which are of no use as a revision.
    """
    ds = _get_dataset(parsed_args)
    if ds is None:
        return []
    repo = ds.repo
    return _startingwith(
        prefix,
        [b for b in repo.get_branches() + repo.get_remote_branches()
         if b.split('/')[-1] != 'git-annex']
        + repo.get_tags(output='name'))


def _get_procedure_names(ds=None):
    # this is the only completer which needs it, and it is not otherwise
    # imported for the completion of other commands
    from datalad.local.run_procedure import _get_procedure_implementation
    return [name for _, name, _, _ in _get_procedure_implementation(ds=ds)]


def complete_procedures(prefix, parsed_args=None, **kwargs):
    """Names of the procedures of `run-procedure`

    Only of the first value: any further one is an argument of the procedure.

    Procedures provided by the dataset are not considered, since their
    discovery requires a traversal of all the subdatasets, which is too slow
    for completion.
    """
    if getattr(parsed_args, 'spec', None):
        return []
    return _startingwith(prefix, _get_procedure_names())


def complete_cfg_procedures(prefix, **kwargs):
    """Names of the ``cfg_`` procedures, without that prefix"""
    return _startingwith(
        prefix,
        (name[4:] for name in _get_procedure_names()
         if name.startswith('cfg_')))


def complete_directories(prefix, parsed_args=None, **kwargs):
    """Directories, relative to any ``-C`` already given on the command line

    Hidden ones are only offered if `prefix` asks for them.
    """
    dirname, partial = os.path.split(prefix)
    try:
        with os.scandir(os.path.join(
                _get_pwd(parsed_args), os.path.expanduser(dirname))) as it:
            names = [e.name for e in it if e.is_dir()]
    except OSError as e:
        lgr.debug("No directories to complete: %s", CapturedException(e))
        return []
    return [
        # trailing separator, so the shell does not consider it complete
        os.path.join(dirname, name, '')
        for name in _startingwith(partial, names)
        if partial.startswith('.') or not name.startswith('.')
    ]


class ChoicesCompleter:
    """Complete with any of the given choices

    Unlike ``choices`` of ``argparse`` it does not limit the acceptable
    values, so is suitable where other values are possible too.
    """
    def __init__(self, *choices):
        self.choices = choices

    def __call__(self, prefix, **kwargs):
        return _startingwith(prefix, self.choices)

    def __repr__(self):
        return f"{self.__class__.__name__}{self.choices!r}"

    def __eq__(self, other):
        return isinstance(other, ChoicesCompleter) \
            and self.choices == other.choices


#: Completers which could be referred to by name in `Parameter.completer`.
#: Extensions could add their own.
completers = {
    'cfg-procedures': complete_cfg_procedures,
    'directories': complete_directories,
    'procedures': complete_procedures,
    'revisions': complete_revisions,
    'siblings': complete_siblings,
}


def _robust(completer):
    """Make `completer` report no candidates instead of raising an exception

    which otherwise would end up as a traceback at the shell prompt.
    """
    @wraps(completer)
    def wrapped(**kwargs):
        try:
            return completer(**kwargs)
        except Exception as e:
            lgr.debug("Completer %r failed: %s",
                      completer, CapturedException(e))
            return []
    # for introspection (and tests)
    wrapped.completer = completer
    return wrapped


def get_completer(spec):
    """Resolve a `Parameter.completer` specification

    Parameters
    ----------
    spec: str or callable or list or tuple
      Name of a known completer (see `completers`), or a completer callable,
      or values to choose from.

    Returns
    -------
    callable or None
      The completer, wrapped to not let any exception through.
      None for an unknown completer name, to fall back on the default
      completion.
    """
    if isinstance(spec, str):
        completer = completers.get(spec)
        if completer is None:
            lgr.warning("Unknown completer %r, known are: %s",
                        spec, ', '.join(sorted(completers)))
            return None
    elif isinstance(spec, (list, tuple)):
        completer = ChoicesCompleter(*spec)
    else:
        completer = spec
    return _robust(completer)


def get_param_completer(param):
    """Return a completer for the values of a `Parameter`

    It is, in order of preference

    - the ``completer`` of the parameter, if specified;
    - directories, if ``constraints`` include `EnsureDataset`;
    - the choices of any `EnsureChoice` among alternative ``constraints``
      (a sole `EnsureChoice` is rather made into ``choices`` of the parser).

    Returns
    -------
    callable or None
      None if there is none, to fall back on the default completion.
    """
    if param.completer is not None:
        return get_completer(param.completer)
    constraints = param.constraints
    if not isinstance(constraints, AltConstraints):
        return get_completer('directories') \
            if isinstance(constraints, EnsureDataset) else None
    if any(isinstance(c, EnsureDataset) for c in constraints.constraints):
        return get_completer('directories')
    choices = [
        choice
        for c in constraints.constraints if isinstance(c, EnsureChoice)
        for choice in c._allowed if isinstance(choice, str)
    ]
    return get_completer(choices) if choices else None
