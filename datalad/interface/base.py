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

from datalad.support.exceptions import InsufficientArgumentsError
from datalad.utils import with_pathsep as _with_sep
from datalad.support.constraints import EnsureKeyChoice
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import resolve_path


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


def update_docstring_with_parameters(func, params, prefix=None, suffix=None):
    """Generate a useful docstring from a parameter spec

    Amends any existing docstring of a callable with a textual
    description of its parameters. The Parameter spec needs to match
    the number and names of the callables arguments.
    """
    from inspect import getargspec
    # get the signature
    ndefaults = 0
    args, varargs, varkw, defaults = getargspec(func)
    if not defaults is None:
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
                if not param.constraints is None:
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


class Interface(object):
    """Base class for interface implementations"""

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
        if cls.__name__ not in (
                'AddArchiveContent', 'AddSibling', 'AggregateMetaData',
                'CrawlInit', 'Crawl', 'CreateSiblingGithub', 'CreateSibling',
                'CreateTestDataset', 'DownloadURL', 'Export', 'Ls', 'Move',
                'Publish', 'SSHRun', 'Search'):
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
                    lambda x, **kwargs: ui.message(args.common_output_format.format(**x))
            if args.common_on_failure:
                kwargs['on_failure'] = args.common_on_failure
            # compose filter function from to be invented cmdline options
            result_filter = None
            if args.common_report_status:
                if args.common_report_status == 'success':
                    result_filter = EnsureKeyChoice('status', ('ok', 'notneeded'))
                elif args.common_report_status == 'failure':
                    result_filter = EnsureKeyChoice('status', ('impossible', 'error'))
                else:
                    result_filter = EnsureKeyChoice('status', (args.common_report_status,))
            if args.common_report_type:
                tfilt = EnsureKeyChoice('type', tuple(args.common_report_type))
                result_filter = result_filter & tfilt if result_filter else tfilt
            kwargs['result_filter'] = result_filter
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
            sys.exit(1)

    @classmethod
    def get_refds_path(cls, dataset):
        """Return a resolved reference dataset path from a `dataset` argument"""
        # theoretically a dataset could come in as a relative path -> resolve
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset
        if refds_path:
            refds_path = resolve_path(refds_path)
        return refds_path

    @staticmethod
    def _prep(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            dir_lookup=None,
            sub_paths=True):
        """Common input argument validation and pre-processing

        This method pre-processes the two most common input argument types:
        a base dataset, and one or more given paths. One or the other needs
        to be different from `None` or an `InsufficientArgumentsError` will
        be raised.

        Paths are normalized based on current practice (if relative, they
        are interpreted relative to a base dataset, if one is provided, or
        relative to the current working directory if not).

        Paths are then sorted by the datasets that contain them. If paths are
        detected that are not associated with any dataset `ValueError` is
        raised. If a `dataset` is given, any paths associated with a dataset
        that is not this dataset or a subdataset of it will also trigger a
        `ValueError`.

        Parameters
        ----------
        path : path or list(path) or None
          Path input argument
        dataset : path or Dataset or None
          Dataset input argument. If given, the output dict is guaranteed
          to carry a key for this dataset, but not necessarily any paths
          as values.
        recursive : bool
          Whether to discover subdatasets under any of the given paths
          recursively
        recursion_limit : None or int
          Optional recursion limit specification (max levels of recursion)
        dir_lookup : dict, optional
          Passed to `get_paths_by_dataset`
        sub_paths : bool, optional
          Passed to `get_paths_by_dataset`  :-P

        Returns
        -------
        (dict, list)
          The dictionary contains keys of absolute dataset paths and lists with
          the normalized (generally absolute) paths of presently existing
          locations associated with the respective dataset as values. The list
          return in addition contains all paths that are part of a dataset, but
          presently do not exist on the filesystem.
        """
        from .utils import get_normalized_path_arguments
        from .utils import get_paths_by_dataset
        # upfront check prior any resolution attempt to avoid disaster
        if path is None and dataset is None:
            raise InsufficientArgumentsError(
                "at least a dataset or a path must be given")

        path, dataset_path = get_normalized_path_arguments(
            path, dataset)
        if not path and dataset_path and recursive:
            # if we have nothing given, but need recursion, we need to feed
            # the dataset path to the sorting to make it work
            # but we also need to fish it out again afterwards
            tosort = [dataset_path]
            fishout_dataset_path = True
        else:
            tosort = path
            fishout_dataset_path = False
        content_by_ds, unavailable_paths, nondataset_paths = \
            get_paths_by_dataset(tosort,
                                 recursive=recursive,
                                 recursion_limit=recursion_limit,
                                 dir_lookup=dir_lookup,
                                 sub_paths=sub_paths)
        if fishout_dataset_path:  # explicit better than implicit, duplication is evil
            # fish out the dataset path that we inserted above
            content_by_ds[dataset_path] = [p for p in content_by_ds[dataset_path]
                                           if p != dataset_path]
        if not path and dataset_path:
            # no files given, but a dataset -> operate on whole dataset
            # but do not specify any paths to process -- needs to be tailored
            # by caller
            content_by_ds[dataset_path] = content_by_ds.get(dataset_path, [])
        if dataset_path and not content_by_ds and not unavailable_paths:
            # we got a dataset, but there is nothing actually installed
            nondataset_paths.append(dataset_path)
        if dataset_path:
            # check that we only got SUBdatasets
            dataset_path = _with_sep(dataset_path)
            for ds in content_by_ds:
                if not _with_sep(ds).startswith(dataset_path):
                    nondataset_paths.extend(content_by_ds[ds])
        # complain about nondataset and non-existing paths
        if nondataset_paths:
            if dataset_path:
                raise ValueError(
                    "will not touch paths outside of base datasets(%s): %s"
                    % (dataset_path, nondataset_paths))
            else:
                raise ValueError(
                    "will not touch paths outside of installed datasets: %s"
                    % nondataset_paths)
        if unavailable_paths:
            lgr.debug('Encountered unavaliable paths: %s', unavailable_paths)
        return content_by_ds, unavailable_paths


def merge_allargs2kwargs(call, args, kwargs):
    """Generate a kwargs dict from a call signature and *args, **kwargs"""
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
    assert (nargs == len(kwargs_))
    return kwargs_
