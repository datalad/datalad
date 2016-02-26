# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

__docformat__ = 'restructuredtext'

# argument spec template
#<name> = (
#    <id_as_positional>, <id_as_option>
#    {<ArgusmentParser.add_arguments_kwargs>}
#)

from ..cmdline.helpers import HelpAction, LogLevelAction

help = (
    'help', ('-h', '--help', '--help-np'),
    dict(nargs=0, action=HelpAction,
         help="""show this help message and exit. --help-np forcefully disables
                 the use of a pager for displaying the help.""")
)

version = (
    'version', ('--version',),
    dict(action='version',
         help="show program's version and license information and exit")
)

log_level = (
    'log-level', ('-l', '--log-level'),
    dict(action=LogLevelAction,
         choices=['critical', 'error', 'warning', 'info', 'debug'] + [str(x) for x in range(1, 10)],
         default='warning',
         help="""level of verbosity. Integers provide even more debugging information""")
)

pbs_runner = (
    'pbs-runner', ('-p', '--pbs-runner'),
    dict(choices=['condor'],
         default=None,
         help="""execute command by scheduling it via available PBS.  For settings config fill be consulted""")
)

