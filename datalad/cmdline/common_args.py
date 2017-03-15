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
#    {<ArgumentParser.add_arguments_kwargs>}
#)

from ..cmdline.helpers import HelpAction, LogLevelAction

help = (
    'help', ('-h', '--help', '--help-np'),
    dict(nargs=0, action=HelpAction,
         help="""show this help message.  --help-np forcefully disables
                 the use of a pager for displaying the help message""")
)

version = (
    'version', ('--version',),
    dict(action='version',
         help="show the program's version and license information")
)

_log_level_names = ['critical', 'error', 'warning', 'info', 'debug']
log_level = (
    'log-level', ('-l', '--log-level'),
    dict(action=LogLevelAction,
         choices=_log_level_names + [str(x) for x in range(1, 10)],
         metavar="LEVEL",
         default='warning',
         help="""set logging verbosity level.  Choose among %s.  Also you can
         specify an integer <10 to provide even more debugging information"""
              % ', '.join(_log_level_names))
)

pbs_runner = (
    'pbs-runner', ('--pbs-runner',),
    dict(choices=['condor'],
         default=None,
         help="""execute command by scheduling it via available PBS.  For settings, config file will be consulted""")
)

change_path = (
    'change-path', ('-C',),
    dict(action='append',
         dest='change_path',
         metavar='PATH',
         help="""run as if datalad was started in <path> instead
         of the current working directory.  When multiple -C options are given,
         each subsequent non-absolute -C <path> is interpreted relative to the
         preceding -C <path>.  This option affects the interpretations of the
         path names in that they are made relative to the working directory
         caused by the -C option""")
)
