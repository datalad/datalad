# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

import sys
import re
import textwrap
import inspect
from collections import OrderedDict

from ..ui import ui
from ..dochelpers import exc_str

from datalad.interface.common_opts import eval_params
from datalad.interface.common_opts import eval_defaults
from datalad.support.constraints import EnsureKeyChoice
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path


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


def get_cmdline_command_name(intfspec):
    """Given an interface specification return a cmdline command name"""
    if len(intfspec) > 2:
        name = intfspec[2]
    else:
        name = intfspec[0].split('.')[-1].replace('_', '-')
    return name


def get_interface_groups():
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
        '\|\| CMDLINE \>\>.*\<\< CMDLINE \|\|',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # clean cmdline in-line bits
    docs = re.sub(
        '\[CMD:\s[^\[\]]*\sCMD\]',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        '\[PY:\s([^\[\]]*)\sPY\]',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE)
    docs = re.sub(
        '\|\| PYTHON \>\>(.*)\<\< PYTHON \|\|',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        '\|\| REFLOW \>\>\n(.*)\<\< REFLOW \|\|',
        lambda match: textwrap.fill(match.group(1)),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    return docs


def alter_interface_docs_for_cmdline(docs):
    """Apply modifications to interface docstrings for cmdline doc use."""
    # central place to alter the impression of docstrings,
    # like removing Python API specific sections, and argument markup
    if not docs:
        return docs
    docs = dedent_docstring(docs)
    # clean cmdline sections
    docs = re.sub(
        '\|\| PYTHON \>\>.*\<\< PYTHON \|\|',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # clean cmdline in-line bits
    docs = re.sub(
        '\[PY:\s[^\[\]]*\sPY\]',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        '\[CMD:\s([^\[\]]*)\sCMD\]',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE)
    docs = re.sub(
        '\|\| CMDLINE \>\>(.*)\<\< CMDLINE \|\|',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # remove :role:`...` RST markup for cmdline docs
    docs = re.sub(
        r':\S+:`[^`]*`[\\]*',
        lambda match: ':'.join(match.group(0).split(':')[2:]).strip('`\\'),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # remove None constraint. In general, `None` on the cmdline means don't
    # give option at all, but specifying `None` explicitly is practically
    # impossible
    docs = re.sub(
        ',\sor\svalue\smust\sbe\s`None`',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # capitalize variables and remove backticks to uniformize with
    # argparse output
    docs = re.sub(
        '`\S*`',
        lambda match: match.group(0).strip('`').upper(),
        docs)
    # clean up sphinx API refs
    docs = re.sub(
        '\~datalad\.api\.\S*',
        lambda match: "`{0}`".format(match.group(0)[13:]),
        docs)
    # Remove RST paragraph markup
    docs = re.sub(
        r'^.. \S+::',
        lambda match: match.group(0)[3:-2].upper(),
        docs,
        flags=re.MULTILINE)
    docs = re.sub(
        '\|\| REFLOW \>\>\n(.*)\<\< REFLOW \|\|',
        lambda match: textwrap.fill(match.group(1)),
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
    from inspect import getargspec
    # get the signature
    ndefaults = 0
    args, varargs, varkw, defaults = getargspec(func)
    if add_args:
        add_argnames = sorted(add_args.keys())
        args.extend(add_argnames)
        defaults = defaults + tuple(add_args[k] for k in add_argnames)
    if defaults is not None:
        ndefaults = len(defaults)
    # start documentation with what the callable brings with it
    doc = prefix if prefix else u''
    if len(args) > 1:
        if len(doc):
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


class Interface(object):
    """Base class for interface implementations"""

    # exit code to return if user-interrupted
    # if None, would just reraise the Exception, so if in --dbg
    # mode would fall into the debugger
    _interrupted_exit_code = 1

    _OLDSTYLE_COMMANDS = (
        'AddArchiveContent', 'CrawlInit', 'Crawl', 'CreateSiblingGithub',
        'CreateTestDataset', 'DownloadURL', 'Export', 'Ls', 'Move', 'SSHRun',
        'Test')

    @classmethod
    def setup_parser(cls, parser):
        # XXX needs safety check for name collisions
        # XXX allow for parser kwargs customization
        parser_kwargs = {}
        from inspect import getargspec
        # get the signature
        ndefaults = 0
        args, varargs, varkw, defaults = getargspec(cls.__call__)
        if not defaults is None:
            ndefaults = len(defaults)
        for i, arg in enumerate(args):
            if not is_api_arg(arg):
                continue
            param = cls._params_[arg]
            defaults_idx = ndefaults - len(args) + i
            cmd_args = param.cmd_args
            if cmd_args is None:
                cmd_args = []
            if not len(cmd_args):
                if defaults_idx >= 0:
                    # dealing with a kwarg
                    template = '--%s'
                else:
                    # positional arg
                    template = '%s'
                # use parameter name as default argument name
                parser_args = (template % arg.replace('_', '-'),)
            else:
                parser_args = [c.replace('_', '-') for c in cmd_args]
            parser_kwargs = param.cmd_kwargs
            if defaults_idx >= 0:
                parser_kwargs['default'] = defaults[defaults_idx]
            help = alter_interface_docs_for_cmdline(param._doc)
            if help and help[-1] != '.':
                help += '.'
            if param.constraints is not None:
                parser_kwargs['type'] = param.constraints
                # include value constraint description and default
                # into the help string
                cdoc = alter_interface_docs_for_cmdline(
                    param.constraints.long_description())
                if cdoc[0] == '(' and cdoc[-1] == ')':
                    cdoc = cdoc[1:-1]
                help += '  Constraints: %s' % cdoc
            if defaults_idx >= 0:
                help += " [Default: %r]" % (defaults[defaults_idx],)
            # create the parameter, using the constraint instance for type
            # conversion
            parser.add_argument(*parser_args, help=help,
                                **parser_kwargs)

    @classmethod
    def call_from_parser(cls, args):
        # XXX needs safety check for name collisions
        from inspect import getargspec
        argspec = getargspec(cls.__call__)
        if argspec[2] is None:
            # no **kwargs in the call receiver, pull argnames from signature
            argnames = getargspec(cls.__call__)[0]
        else:
            # common options
            # XXX define or better get from elsewhere
            common_opts = ('change_path', 'common_debug', 'common_idebug', 'func',
                           'help', 'log_level', 'logger', 'pbs_runner',
                           'result_renderer', 'subparser')
            argnames = [name for name in dir(args)
                        if not (name.startswith('_') or name in common_opts)]
        kwargs = {k: getattr(args, k) for k in argnames if is_api_arg(k)}
        # we are coming from the entry point, this is the toplevel command,
        # let it run like generator so we can act on partial results quicker
        # TODO remove following condition test when transition is complete and
        # run indented code unconditionally
        if cls.__name__ not in Interface._OLDSTYLE_COMMANDS:
            # set all common args explicitly  to override class defaults
            # that are tailored towards the the Python API
            kwargs['return_type'] = 'generator'
            kwargs['result_xfm'] = None
            # allow commands to override the default, unless something other than
            # default is requested
            kwargs['result_renderer'] = \
                args.common_output_format if args.common_output_format != 'default' \
                else getattr(cls, 'result_renderer', args.common_output_format)
            if '{' in args.common_output_format:
                # stupid hack, could and should become more powerful
                kwargs['result_renderer'] = \
                    lambda x, **kwargs: ui.message(args.common_output_format.format(
                        **{k: {k_.replace(':', '#'): v_ for k_, v_ in v.items()}
                           if isinstance(v, dict) else v
                           for k, v in x.items()}))
            if args.common_on_failure:
                kwargs['on_failure'] = args.common_on_failure
            # compose filter function from to be invented cmdline options
            res_filter = cls._get_result_filter(args)
            if res_filter is not None:
                # Don't add result_filter if it's None because then
                # eval_results can't distinguish between --report-{status,type}
                # not specified via the CLI and None passed via the Python API.
                kwargs['result_filter'] = res_filter
        try:
            ret = cls.__call__(**kwargs)
            if inspect.isgenerator(ret):
                ret = list(ret)
            if args.common_output_format == 'tailored' and \
                    hasattr(cls, 'custom_result_summary_renderer'):
                cls.custom_result_summary_renderer(ret)
            return ret
        except KeyboardInterrupt as exc:
            ui.error("\nInterrupted by user while doing magic: %s" % exc_str(exc))
            if cls._interrupted_exit_code is not None:
                sys.exit(cls._interrupted_exit_code)
            else:
                raise

    @classmethod
    def _get_result_filter(cls, args):
        from datalad import cfg
        result_filter = None
        if args.common_report_status or 'datalad.runtime.report-status' in cfg:
            report_status = args.common_report_status or \
                            cfg.obtain('datalad.runtime.report-status')
            if report_status == "all":
                pass  # no filter
            elif report_status == 'success':
                result_filter = EnsureKeyChoice('status', ('ok', 'notneeded'))
            elif report_status == 'failure':
                result_filter = EnsureKeyChoice('status',
                                                ('impossible', 'error'))
            else:
                result_filter = EnsureKeyChoice('status', (report_status,))
        if args.common_report_type:
            tfilt = EnsureKeyChoice('type', tuple(args.common_report_type))
            result_filter = result_filter & tfilt if result_filter else tfilt
        return result_filter

    @classmethod
    def get_refds_path(cls, dataset):
        """Return a resolved reference dataset path from a `dataset` argument"""
        # theoretically a dataset could come in as a relative path -> resolve
        if dataset is None:
            return dataset
        refds_path = dataset.path if isinstance(dataset, Dataset) \
            else Dataset(dataset).path
        if refds_path:
            refds_path = resolve_path(refds_path)
        return refds_path


def get_allargs_as_kwargs(call, args, kwargs):
    """Generate a kwargs dict from a call signature and *args, **kwargs

    Basically resolving the argnames for all positional arguments, and
    resolvin the defaults for all kwargs that are not given in a kwargs
    dict
    """
    from inspect import getargspec
    argspec = getargspec(call)
    defaults = argspec.defaults
    nargs = len(argspec.args)
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
