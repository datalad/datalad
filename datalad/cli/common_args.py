# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

__docformat__ = 'restructuredtext'

__all__ = ['common_args']

from .helpers import (
    HelpAction,
    LogLevelAction,
)
from datalad.interface.base import eval_params
from datalad.utils import ensure_unicode


_log_level_names = ['critical', 'error', 'warning', 'info', 'debug']

# argument spec template
#<name>=(
#    <id_as_positional>, <id_as_option>
#    {<ArgumentParser.add_arguments_kwargs>}
#)

common_args = dict(
    cfg_overrides=(
        ('-c',),
        dict(action='append',
             dest='cfg_overrides',
             metavar='(:name|name=value)',
             help="""specify configuration setting overrides. They override any
             configuration read from a file. A configuration can also be
             unset temporarily by prefixing its name with a colon (':'), e.g. ':user.name'.
             Overrides specified here may be overridden themselves by
             configuration settings declared as environment variables.
             """)),
    change_path=(
        ('-C',),
        dict(action='append',
             dest='change_path',
             metavar='PATH',
             help="""run as if datalad was started in <path> instead
             of the current working directory.  When multiple -C options are given,
             each subsequent non-absolute -C <path> is interpreted relative to the
             preceding -C <path>.  This option affects the interpretations of the
             path names in that they are made relative to the working directory
             caused by the -C option""")),
    cmd=(
        ('--cmd',),
        dict(dest='_',
             action='store_true',
             help="""syntactical helper that can be used to end the list of
             global command line options before the subcommand label. Options
             taking an arbitrary number of arguments may require to be followed
             by a single --cmd in order to enable identification of the
             subcommand.""")),
    help=(
        ('-h', '--help', '--help-np'),
        dict(nargs=0, action=HelpAction,
             help="""show this help message.  --help-np forcefully disables
                     the use of a pager for displaying the help message""")),
    log_level=(
        ('-l', '--log-level'),
        dict(action=LogLevelAction,
             choices=_log_level_names + [str(x) for x in range(1, 10)],
             metavar="LEVEL",
             default='warning',
             help="""set logging verbosity level.  Choose among %s.  Also you can
             specify an integer <10 to provide even more debugging
             information""" % ', '.join(_log_level_names))),
    # CLI analog of eval_params.on_failure. TODO: dedup
    on_failure=(
        ('--on-failure',),
        dict(dest='common_on_failure',
             # setting the default to None here has the following implications
             # - the global default is solely defined in
             #   datalad.interface.common_opts.eval_params and is in-effect for
             #   Python API and CLI
             # - this global default is written to each command Interface class
             #   and can be overridden there on a per-command basis, with such
             #   override being honored by both APIs
             # - the CLI continues to advertise the choices defined below as
             #   the possible values for '--on-failure'
             # - the Python docstring reflects a possibly command-specific
             #   default
             default=None,
             choices=['ignore', 'continue', 'stop'],
             help="""when an operation fails: 'ignore' and continue with
             remaining operations, the error is logged but does not lead to a
             non-zero exit code of the command; 'continue' works like 'ignore',
             but an error causes a non-zero exit code; 'stop' halts on first
             failure and yields non-zero exit code. A failure is any result
             with status 'impossible' or 'error'. [Default: '%s', but
             individual commands may define an alternative default]"""
             % eval_params['on_failure'].cmd_kwargs['default'])),
    report_status=(
        ('--report-status',),
        dict(dest='common_report_status',
             choices=['success', 'failure', 'ok', 'notneeded', 'impossible',
                      'error'],
             help="""constrain command result report to records matching the
             given status. 'success' is a synonym for 'ok' OR 'notneeded',
             'failure' stands for 'impossible' OR 'error'.""")),
    report_type=(
        ('--report-type',),
        dict(dest='common_report_type',
             choices=['dataset', 'file'],
             action='append',
             help="""constrain command result report to records matching the
             given type. Can be given more than once to match multiple types.
             """)),
    # CLI analog of eval_params.result_renderer but with `<template>` handling
    # and a different default: in Python API we have None as default and do not
    # render the results but return them.  In CLI we default to "default"
    # renderer
    result_renderer=(
        # this should really have --result-renderer for homogeneity with the
        # Python API, but adding it in addition makes the help output
        # monsterous
        ('-f', '--output-format'), # '--result-renderer',
        dict(dest='common_result_renderer',
             default='tailored',
             type=ensure_unicode,
             metavar="{generic,json,json_pp,tailored,disabled,'<template>'}",
             help=eval_params['result_renderer']._doc \
             + " [Default: '%(default)s']")),
)

if __debug__:
    common_args.update(
        dbg=(
            ('--dbg',),
            dict(action='store_true',
                 dest='common_debug',
                 help="enter Python debugger for an uncaught exception",
            )),
        idbg=(
            ('--idbg',),
            dict(action='store_true',
                 dest='common_idebug',
                 help="enter IPython debugger for an uncaught exception")),
    )
