# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface generation

"""

__docformat__ = 'restructuredtext'

import logging
lgr = logging.getLogger('datalad.interface.base')

from abc import (
    ABC,
    abstractmethod,
)
import os
import re
import textwrap
from importlib import import_module
from collections import (
    OrderedDict,
)
import warnings

import datalad
from datalad.interface.common_opts import eval_params
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path
from datalad.support.exceptions import CapturedException


default_logchannels = {
    '': 'debug',
    'ok': 'debug',
    'notneeded': 'debug',
    'impossible': 'warning',
    'error': 'error',
}


def get_api_name(intfspec):
    """Given an interface specification return an API name for it"""
    if len(intfspec) > 3:
        name = intfspec[3]
    else:
        name = intfspec[0].split('.')[-1]
    return name


def get_interface_groups(include_plugins=False):
    """Return a list of command groups.

    Returns
    -------
    A list of tuples with the form (GROUP_NAME, GROUP_DESCRIPTION, COMMANDS).
    """
    if include_plugins:
        warnings.warn("Plugins are no longer supported.", DeprecationWarning)

    from .. import interface as _interfaces

    grps = []
    # auto detect all available interfaces and generate a function-based
    # API from them
    for _item in _interfaces.__dict__:
        if not _item.startswith('_group_'):
            continue
        grp_name = _item[7:]
        grp = getattr(_interfaces, _item)
        grps.append((grp_name,) + grp)
    return grps


def get_cmd_summaries(descriptions, groups, width=79):
    """Return summaries for the commands in `groups`.

    Parameters
    ----------
    descriptions : dict
        A map of group names to summaries.
    groups : list of tuples
        A list of groups and commands in the form described by
        `get_interface_groups`.
    width : int, optional
        The maximum width of each line in the summary text.

    Returns
    -------
    A list with a formatted entry for each command. The first command of each
    group is preceded by an entry describing the group.
    """
    cmd_summary = []
    for grp in sorted(groups, key=lambda x: x[0]):
        grp_descr = grp[1]
        grp_cmds = descriptions[grp[0]]

        cmd_summary.append('\n*%s*\n' % (grp_descr,))
        for cd in grp_cmds:
            cmd_summary.append('  %s\n%s'
                               % ((cd[0],
                                   textwrap.fill(
                                       cd[1].rstrip(' .'),
                                       width - 5,
                                       initial_indent=' ' * 6,
                                       subsequent_indent=' ' * 6))))
    return cmd_summary


def load_interface(spec):
    """Load and return the class for `spec`.

    Parameters
    ----------
    spec : tuple
        For a standard interface, the first item is the datalad source module
        and the second object name for the interface.

    Returns
    -------
    The interface class or, if importing the module fails, None.
    """
    lgr.log(5, "Importing module %s ", spec[0])
    try:
        mod = import_module(spec[0], package='datalad')
    except Exception as e:
        ce = CapturedException(e)
        lgr.error("Internal error, cannot import interface '%s': %s",
                  spec[0], ce)
        intf = None
    else:
        intf = getattr(mod, spec[1])
    return intf


def get_cmd_doc(interface):
    """Return the documentation for the command defined by `interface`.

    Parameters
    ----------
    interface : subclass of Interface
    """
    intf_doc = '' if interface.__doc__ is None else interface.__doc__.strip()
    if hasattr(interface, '_docs_'):
        # expand docs
        intf_doc = intf_doc.format(**interface._docs_)
    return intf_doc


def dedent_docstring(text):
    """Remove uniform indentation from a multiline docstring"""
    # Problem is that first line might often have no offset, so might
    # need to be ignored from dedent call
    if text is None:
        return None
    if not text.startswith(' '):
        lines = text.split('\n')
        if len(lines) == 1:
            # single line, no indentation, nothing to do
            return text
        text2 = '\n'.join(lines[1:])
        return lines[0] + "\n" + textwrap.dedent(text2)
    else:
        return textwrap.dedent(text)


def alter_interface_docs_for_api(docs):
    """Apply modifications to interface docstrings for Python API use."""
    # central place to alter the impression of docstrings,
    # like removing cmdline specific sections
    if not docs:
        return docs
    docs = dedent_docstring(docs)
    # clean cmdline sections
    docs = re.sub(
        r'\|\| CMDLINE \>\>.*?\<\< CMDLINE \|\|',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # clean cmdline in-line bits
    docs = re.sub(
        r'\[CMD:\s[^\[\]]*\sCMD\]',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        r'\[PY:\s([^\[\]]*)\sPY\]',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE)
    # select only the python alternative from argument specifications
    docs = re.sub(
        r'``([a-zA-Z0-9_,.]+)\|\|([a-zA-Z0-9-,.]+)``',
        lambda match: f'``{match.group(1)}``',
        docs)
    docs = re.sub(
        r'\|\| PYTHON \>\>(.*?)\<\< PYTHON \|\|',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    if 'DATALAD_SPHINX_RUN' not in os.environ:
        # remove :role:`...` RST markup for cmdline docs
        docs = re.sub(
            r':\S+:`[^`]*`[\\]*',
            lambda match: ':'.join(match.group(0).split(':')[2:]).strip('`\\'),
            docs,
            flags=re.MULTILINE | re.DOTALL)
        # make the handbook doc references more accessible
        # the URL is a redirect configured at readthedocs
        docs = re.sub(
            r'(handbook:[0-9]-[0-9]*)',
            '\\1 (http://handbook.datalad.org/symbols)',
            docs)
    docs = re.sub(
        r'^([ ]*)\|\| REFLOW \>\>\n(.*?)\<\< REFLOW \|\|',
        lambda match: textwrap.fill(match.group(2), subsequent_indent=match.group(1)),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    return docs


def is_api_arg(arg):
    """Return True if argument is our API argument or self or used for internal
    purposes
    """
    return arg != 'self' and not arg.startswith('_')


def update_docstring_with_parameters(func, params, prefix=None, suffix=None,
                                     add_args=None):
    """Generate a useful docstring from a parameter spec

    Amends any existing docstring of a callable with a textual
    description of its parameters. The Parameter spec needs to match
    the number and names of the callables arguments.
    """
    from datalad.utils import getargspec
    # get the signature
    args, varargs, varkw, defaults = getargspec(func, include_kwonlyargs=True)
    defaults = defaults or tuple()
    if add_args:
        add_argnames = sorted(add_args.keys())
        args.extend(add_argnames)
        defaults = defaults + tuple(add_args[k] for k in add_argnames)
    ndefaults = len(defaults)
    # start documentation with what the callable brings with it
    doc = prefix if prefix else u''
    if len(args) > 1:
        if len(doc):
            if not doc.endswith('\n'):
                doc += '\n'
            doc += '\n'
        doc += "Parameters\n----------\n"
        for i, arg in enumerate(args):
            if not is_api_arg(arg):
                continue
            # we need a parameter spec for each argument
            if not arg in params:
                raise ValueError("function has argument '%s' not described as a parameter" % arg)
            param = params[arg]
            # validate the default -- to make sure that the parameter description is
            # somewhat OK
            defaults_idx = ndefaults - len(args) + i
            if defaults_idx >= 0:
                if param.constraints is not None:
                    param.constraints(defaults[defaults_idx])
            orig_docs = param._doc
            param._doc = alter_interface_docs_for_api(param._doc)
            doc += param.get_autodoc(
                arg,
                default=defaults[defaults_idx] if defaults_idx >= 0 else None,
                has_default=defaults_idx >= 0)
            param._doc = orig_docs
            doc += '\n'
    doc += suffix if suffix else u""
    # assign the amended docs
    func.__doc__ = doc
    return func


# TODO should export code_field and indicator, rather than have modes
# TODO this should be a doc helper
def build_example(example, api='python'):
    """Build a code example.

    Take a dict from a classes _example_ specification (list of dicts) and
    build a string with an api or cmd example (for use in cmd help or
    docstring).

    Parameters
    ----------
    api : {'python', 'cmdline'}
        If 'python', build Python example for docstring. If 'cmdline', build
        cmd example.

    Returns
    -------
    ex : str
        Concatenated examples for the given class.
    """
    if api == 'python' :
        code_field='code_py'
        indicator='>'
    elif api == 'cmdline':
        code_field='code_cmd'
        indicator='%'
    else:
        raise ValueError("unknown API selection: {}".format(api))
    if code_field not in example:
        # only show an example if it exist for the API
        return ''
    description = textwrap.fill(example.get('text'))
    # this indent the code snippet to get it properly rendered as code
    # we are not using textwrap.fill(), because it would not acknowledge
    # any meaningful structure/formatting of code snippets. Instead, we
    # maintain line content as is.
    code = dedent_docstring(example.get(code_field))
    needs_indicator = not code.startswith(indicator)
    code = textwrap.indent(code, ' ' * (5 if needs_indicator else 3)).lstrip()

    ex = """{}::\n\n   {}{}\n\n""".format(
        description,
        # disable automatic prefixing, if the example already has one
        # this enables providing more complex examples without having
        # to infer its inner structure
        '{} '.format(indicator)
        if needs_indicator
        # maintain spacing to avoid undesired relative indentation
        else '',
        code)

    return ex


def update_docstring_with_examples(cls_doc, ex):
    """Update a commands docstring with examples.

    Take _examples_ of a command, build the Python examples, and append
    them to the docstring.

    Parameters
    ----------
    cls_doc: str
      docstring
    ex: list
      list of dicts with examples
    """
    from textwrap import indent
    if len(cls_doc):
        cls_doc += "\n"
    cls_doc += "    Examples\n    --------\n"
    # loop though provided examples
    for example in ex:
        cls_doc += indent(build_example(example, api='python'), ' '*4)

    return cls_doc


def build_doc(cls, **kwargs):
    """Decorator to build docstrings for datalad commands

    It's intended to decorate the class, the __call__-method of which is the
    actual command. It expects that __call__-method to be decorated by
    eval_results.

    Note that values for any `eval_params` keys in `cls._params_` are
    ignored.  This means one class may extend another's `_params_`
    without worrying about filtering out `eval_params`.

    Parameters
    ----------
    cls: Interface
      DataLad command implementation
    """
    if datalad.in_librarymode():
        lgr.debug("Not assembling DataLad API docs in libary-mode")
        return cls

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
    # get examples
    ex = getattr(cls, '_examples_', [])
    if ex:
        cls_doc = update_docstring_with_examples(cls_doc, ex)

    call_doc = None
    # suffix for update_docstring_with_parameters:
    if cls.__call__.__doc__:
        call_doc = cls.__call__.__doc__

    # build standard doc and insert eval_doc
    spec = getattr(cls, '_params_', dict())


    # update class attributes that may override defaults
    if not _has_eval_results_call(cls):
        add_args = None
    else:
        # defaults for all common parameters are guaranteed to be available
        # from the class
        add_args = {k: getattr(cls, k) for k in eval_params}

    # ATTN: An important consequence of this update() call is that it
    # fulfills the docstring's promise of overriding any existing
    # values for eval_params keys in _params_.
    #

    # get docs for eval_results parameters:
    spec.update(eval_params)

    update_docstring_with_parameters(
        cls.__call__, spec,
        prefix=alter_interface_docs_for_api(cls_doc),
        suffix=alter_interface_docs_for_api(call_doc),
        add_args=add_args
    )

    if hasattr(cls.__call__, '_dataset_method'):
        cls.__call__._dataset_method.__doc__ = cls.__call__.__doc__

    # return original
    return cls


class Interface(ABC):
    '''Abstract base class for DataLad command implementations

    Any DataLad command implementation must be derived from this class. The
    code snippet below shows a complete sketch of a Python class with such an
    implementation.

    Importantly, no instances of command classes will created. Instead the main
    entry point is a static ``__call__()`` method, which must be implemented
    for any command. It is incorporated as a function in :mod:`datalad.api`, by
    default under the name of the file the implementation resides (e.g.,
    ``command`` for a ``command.py`` file).  Therefore the file should have a
    name that is a syntax-compliant function name. The default naming rule can
    be overwritten with an explicit alternative name (see
    :func:`datalad.interface.base.get_api_name`).

    For commands implementing functionality that is operating on DataLad
    datasets, a command can be also be bound to the
    :class:`~datalad.distribution.dataset.Dataset` class as a method using
    the ``@datasetmethod`` decorator, under the specified name.

    Any ``__call__()`` implementation should be decorated with
    :func:`datalad.interface.utils.eval_results`. This adds support for
    standard result processing, and a range of common command parameters that
    do not need to be manually added to the signature of ``__call__()``. Any
    implementation decorated in this way should be implemented as a generator,
    and ``yield`` :ref:`result records <chap_design_result_records>`.

    Any argument or keyword argument that appears in the signature of
    ``__call__()`` must have a matching item in :attr:`Interface._params_`.
    The dictionary maps argument names to
    :class:`datalad.support.param.Parameter` specifications. The specification
    contain CLI argument declarations, value constraint and data type
    conversation specifications, documentation, and optional
    ``argparse``-specific arguments for CLI parser construction.

    The class decorator :func:`datalad.interface.base.build_doc` inspects an
    :class:`Interface` implementation, and builds a standard docstring from
    various sources of structured information within the class (also see
    below). The documentation is automatically tuned differently, depending on
    the target API (Python vs CLI).

    .. code:: python

        @build_doc
        class ExampleCommand(Interface):
            """SHORT DESCRIPTION

            LONG DESCRIPTION
            ...
            """

            # COMMAND PARAMETER DEFINITIONS
            _params_ = dict(
                example=Parameter(
                    args=("--example",),
                    doc="""Parameter description....""",
                    constraints=...),
                ...
                )
            )

            # RESULT PARAMETER OVERRIDES
            return_type= 'list'
            ...

            # USAGE EXAMPLES
            _examples_ = [
                dict(text="Example description...",
                     code_py="Example Python code...",
                     code_cmd="Example shell code ..."),
                ...
            ]

            @staticmethod
            @datasetmethod(name='example_command')
            @eval_results
            def __call__(example=None, ...):
                ...

                yield dict(...)

    The basic implementation setup described above can be customized for
    individual commands in various way that alter the behavior and
    presentation of a specific command. The following overview uses
    the code comment markers in the above snippet to illustrate where
    in the class implementation these adjustments can be made.

    (SHORT/LONG) DESCRIPTION

    ``Interface.short_description`` can be defined to provide an
    explicit short description to be used in documentation and help output,
    replacing the auto-generated extract from the first line of the full
    description.

    COMMAND PARAMETER DEFINITIONS

    When a parameter specification declares ``Parameter(args=tuple(), ...)``,
    i.e. no arguments specified, it will be ignored by the CLI. Likewise, any
    ``Parameter`` specification for which :func:`is_api_arg` returns ``False``
    will also be ignored by the CLI. Additionally, any such parameter will
    not be added to the parameter description list in the Python docstring.

    RESULT PARAMETER OVERRIDES

    The :func:`datalad.interface.utils.eval_results` decorator automatically
    add a range of additional arguments to a command, which are defined in
    :py:data:`datalad.interface.common_opts.eval_params`. For any such
    parameter an Interface implementation can define an interface-specific
    default value, by declaring a class member with the respective parameter
    name and the desired default as its assigned value. This feature can be
    used to tune the default command behavior, for example, with respect to the
    default result rendering style, or its error behavior.

    In addition to the common parameters of the Python API, an additional
    ``Interface.result_renderer_cmdline`` can be defined, in order to
    instruct the CLI to prefer the specified alternative result renderer
    over an ``Interface.result_renderer`` specification.

    USAGE EXAMPLES

    Any number of usage examples can be described in an ``_examples_`` list
    class attribute. Such an example contains a description, and code examples
    for Python and CLI.
    '''
    _params_ = {}

    @abstractmethod
    def __call__():
        """Must be implemented by any command"""

    # https://github.com/datalad/datalad/issues/6376
    @classmethod
    def get_refds_path(cls, dataset):
        """Return a resolved reference dataset path from a `dataset` argument

        .. deprecated:: 0.16
           Use ``require_dataset()`` instead.
        """
        # theoretically a dataset could come in as a relative path -> resolve
        if dataset is None:
            return dataset
        refds_path = dataset.path if isinstance(dataset, Dataset) \
            else Dataset(dataset).path
        if refds_path:
            refds_path = str(resolve_path(refds_path))
        return refds_path


# pull all defaults from all eval_results() related parameters and assign them
# as attributes to the class, which then becomes the one place to query for
# default and potential overrides
for k, p in eval_params.items():
    setattr(Interface,
            # name is always given
            k,
            # but there may be no default (rather unlikely, though)
            p.cmd_kwargs.get('default', None))


def get_allargs_as_kwargs(call, args, kwargs):
    """Generate a kwargs dict from a call signature and ``*args``, ``**kwargs``

    Basically resolving the argnames for all positional arguments, and
    resolving the defaults for all kwargs that are not given in a kwargs
    dict
    """
    from datalad.utils import getargspec
    argspec = getargspec(call, include_kwonlyargs=True)
    defaults = argspec.defaults
    nargs = len(argspec.args)
    defaults = defaults or []  # ensure it is a list and not None
    assert (nargs >= len(defaults))
    # map any args to their name
    argmap = list(zip(argspec.args[:len(args)], args))
    kwargs_ = OrderedDict(argmap)
    # map defaults of kwargs to their names (update below)
    for k, v in zip(argspec.args[-len(defaults):], defaults):
        if k not in kwargs_:
            kwargs_[k] = v
    # update with provided kwarg args
    kwargs_.update(kwargs)
    # XXX we cannot assert the following, because our own highlevel
    # API commands support more kwargs than what is discoverable
    # from their signature...
    #assert (nargs == len(kwargs_))
    return kwargs_


# Only needed to support command implementations before the introduction
# of @eval_results
def _has_eval_results_call(cls):
    """Return True if cls has a __call__ decorated with @eval_results
    """
    return getattr(getattr(cls, '__call__', None), '_eval_results', False)
