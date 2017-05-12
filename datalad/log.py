# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import os
import sys
import platform
import logging.handlers

from os.path import basename, dirname

from .utils import is_interactive
from .support import ansi_colors as colors

__all__ = ['ColorFormatter']

# Snippets from traceback borrowed from duecredit which was borrowed from
# PyMVPA upstream/2.4.0-39-g69ad545  MIT license (the same copyright as DataLad)


def mbasename(s):
    """Custom function to include directory name if filename is too common

    Also strip .py at the end
    """
    base = basename(s)
    if base.endswith('.py'):
        base = base[:-3]
    if base in set(['base', '__init__']):
        base = basename(dirname(s)) + '.' + base
    return base


class TraceBack(object):
    """Customized traceback to be included in debug messages
    """

    def __init__(self, limit=100, collide=False):
        """Initialize TraceBack metric

        Parameters
        ----------
        collide : bool
          if True then prefix common with previous invocation gets
          replaced with ...
        """
        self.__prev = ""
        self.limit = limit
        self.collide = collide

        # delayed imports and preparing the regex substitution
        if collide:
            import re
            self.__prefix_re = re.compile('>[^>]*$')
        else:
            self.__prefix_re = None

        import traceback
        self._extract_stack = traceback.extract_stack

    def __call__(self):
        ftb = self._extract_stack(limit=200)[:-2]
        entries = [[mbasename(x[0]), str(x[1])]
                   for x in ftb if mbasename(x[0]) != 'logging.__init__']
        entries = [e for e in entries if e[0] != 'unittest']

        if len(entries) > self.limit:
            sftb = '...>'
            entries = entries[-self.limit:]
        else:
            sftb = ''

        if not entries:
            return ""

        # lets make it more consize
        entries_out = [entries[0]]
        for entry in entries[1:]:
            if entry[0] == entries_out[-1][0]:
                entries_out[-1][1] += ',%s' % entry[1]
            else:
                entries_out.append(entry)

        sftb += '>'.join(
            ['%s:%s' % (mbasename(x[0]), x[1]) for x in entries_out]
        )

        if self.collide:
            # lets remove part which is common with previous invocation
            prev_next = sftb
            common_prefix = os.path.commonprefix((self.__prev, sftb))
            common_prefix2 = self.__prefix_re.sub('', common_prefix)

            if common_prefix2 != "":
                sftb = '...' + sftb[len(common_prefix2):]
            self.__prev = prev_next

        return sftb


# Recipe from http://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
# by Brandon Thomson
# Adjusted for automagic determination either coloring is needed and
# prefixing of multiline log lines
class ColorFormatter(logging.Formatter):

    def __init__(self, use_color=None, log_name=False, log_pid=False):
        if use_color is None:
            # if 'auto' - use color only if all streams are tty
            use_color = is_interactive()
        self.use_color = use_color and platform.system() != 'Windows'  # don't use color on windows
        msg = colors.format_msg(self._get_format(log_name, log_pid),
                                self.use_color)
        log_env = os.environ.get('DATALAD_LOG_TRACEBACK', '')
        collide = log_env == 'collide'
        limit = 100 if collide else int(log_env) if log_env.isdigit() else 100
        self._tb = TraceBack(collide=collide, limit=limit) if log_env else None
        logging.Formatter.__init__(self, msg)

    def _get_format(self, log_name=False, log_pid=False):
        from datalad import cfg
        from datalad.config import anything2bool
        show_timestamps = anything2bool(cfg.get('datalad.log.timestamp', False))
        return (("" if not show_timestamps else "$BOLD%(asctime)-15s$RESET ") +
                ("%(name)-15s " if log_name else "") +
                ("{%(process)d}" if log_pid else "") +
                "[%(levelname)s] "
                "%(message)s ")

    def format(self, record):
        if record.msg.startswith('| '):
            # If we already log smth which supposed to go without formatting, like
            # output for running a command, just return the message and be done
            return record.msg

        levelname = record.levelname

        if self.use_color and levelname in colors.LOG_LEVEL_COLORS:
            fore_color = colors.LOG_LEVEL_COLORS[levelname]
            levelname_color = (colors.COLOR_SEQ % fore_color) + \
                              ("%-7s" % levelname) + colors.RESET_SEQ
            record.levelname = levelname_color
        record.msg = record.msg.replace("\n", "\n| ")
        if self._tb:
            record.msg = self._tb() + "  " + record.msg

        return logging.Formatter.format(self, record)


class LoggerHelper(object):
    """Helper to establish and control a Logger"""

    def __init__(self, name='datalad', logtarget=None):
        """

        Parameters
        ----------
        name :
        logtarget : string, optional
          If we want to use our logger for other log targets, while having
          a uniform control over them
        """
        self.name = name
        self.logtarget = logtarget
        self.lgr = logging.getLogger(logtarget if logtarget is not None else name)

    def _get_config(self, var, default=None):
        from datalad import cfg
        return cfg.get(self.name.lower() + '.log.' + var, default)

    def set_level(self, level=None, default='INFO'):
        """Helper to set loglevel for an arbitrary logger

        By default operates for 'datalad'.
        TODO: deduce name from upper module name so it could be reused without changes
        """
        if level is None:
            # see if nothing in the environment
            level = self._get_config('level')
        if level is None:
            level = default

        try:
            # it might be a string which still represents an int
            log_level = int(level)
        except ValueError:
            # or a string which corresponds to a constant;)
            log_level = getattr(logging, level.upper())

        self.lgr.setLevel(log_level)
        # and set other related/used loggers to the same level to prevent their
        # talkativity, if they are not yet known to this python session, so we
        # have little chance to "override" possibly set outside levels
        for dep in ('git',):
            if dep not in logging.Logger.manager.loggerDict:
                logging.getLogger(dep).setLevel(log_level)

    def get_initialized_logger(self, logtarget=None):
        """Initialize and return the logger

        Parameters
        ----------
        target: string, optional
          Which log target to request logger for
        logtarget: { 'stdout', 'stderr', str }, optional
          Where to direct the logs.  stdout and stderr stand for standard streams.
          Any other string is considered a filename.  Multiple entries could be
          specified comma-separated

        Returns
        -------
        logging.Logger
        """
        # By default mimic previously talkative behavior
        logtarget = self._get_config('target', logtarget or 'stderr')

        # Allow for multiple handlers being specified, comma-separated
        if ',' in logtarget:
            for handler_ in logtarget.split(','):
                self.get_initialized_logger(logtarget=handler_)
            return self.lgr

        if logtarget.lower() in ('stdout', 'stderr'):
            loghandler = logging.StreamHandler(getattr(sys, logtarget.lower()))
            use_color = is_interactive()  # explicitly decide here
        else:
            # must be a simple filename
            # Use RotatingFileHandler for possible future parametrization to keep
            # log succinct and rotating
            loghandler = logging.handlers.RotatingFileHandler(logtarget)
            use_color = False
            # I had decided not to guard this call and just raise exception to go
            # out happen that specified file location is not writable etc.

        for names_filter in 'names', 'namesre':
            names = self._get_config(names_filter, '')
            if names:
                import re
                # add a filter which would catch those
                class LogFilter(object):
                    """A log filter to filter based on the log target name(s)"""
                    def __init__(self, names):
                        self.target_names = set(n for n in names.split(',')) \
                            if names_filter == 'names' \
                            else re.compile(names)
                    if names_filter == 'names':
                        def filter(self, record):
                            return record.name in self.target_names
                    else:
                        def filter(self, record):
                            return self.target_names.match(record.name)

                loghandler.addFilter(LogFilter(names))

        # But now improve with colors and useful information such as time
        loghandler.setFormatter(
            ColorFormatter(use_color=use_color,
                           # TODO: config log.name, pid
                           log_name=self._get_config("name", False),
                           log_pid=self._get_config("pid", False),
                           ))
        #  logging.Formatter('%(asctime)-15s %(levelname)-6s %(message)s'))
        self.lgr.addHandler(loghandler)

        self.set_level()  # set default logging level
        return self.lgr

lgr = LoggerHelper().get_initialized_logger()
