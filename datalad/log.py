# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging, os, sys, platform
import logging.handlers

from .utils import is_interactive

__all__ = ['ColorFormatter', 'log']

# Snippets from traceback borrowed from duecredit which was borrowed from
# PyMVPA upstream/2.4.0-39-g69ad545  MIT license (the same copyright as DataLad)

import traceback
import re
from os.path import basename, dirname

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

    def __init__(self, collide=False):
        """Initialize TrackBack metric

        Parameters
        ----------
        collide : bool
          if True then prefix common with previous invocation gets
          replaced with ...
        """
        self.__prev = ""
        self.__collide = collide

    def __call__(self):
        ftb = traceback.extract_stack(limit=100)[:-2]
        entries = [[mbasename(x[0]), str(x[1])] for x in ftb if mbasename(x[0]) != 'logging.__init__']
        entries = [e for e in entries if e[0] != 'unittest']

        # lets make it more consize
        entries_out = [entries[0]]
        for entry in entries[1:]:
            if entry[0] == entries_out[-1][0]:
                entries_out[-1][1] += ',%s' % entry[1]
            else:
                entries_out.append(entry)
        sftb = '>'.join(['%s:%s' % (mbasename(x[0]),
                                    x[1]) for x in entries_out])
        if self.__collide:
            # lets remove part which is common with previous invocation
            prev_next = sftb
            common_prefix = os.path.commonprefix((self.__prev, sftb))
            common_prefix2 = re.sub('>[^>]*$', '', common_prefix)

            if common_prefix2 != "":
                sftb = '...' + sftb[len(common_prefix2):]
            self.__prev = prev_next

        return sftb


# Recipe from http://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
# by Brandon Thomson
# Adjusted for automagic determination either coloring is needed and
# prefixing of multiline log lines
class ColorFormatter(logging.Formatter):

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[1;%dm"
    BOLD_SEQ = "\033[1m"

    COLORS = {
      'WARNING': YELLOW,
      'INFO': WHITE,
      'DEBUG': BLUE,
      'CRITICAL': YELLOW,
      'ERROR': RED
    }

    def __init__(self, use_color=None, log_name=False, log_pid=False):
        if use_color is None:
            # if 'auto' - use color only if all streams are tty
            use_color = is_interactive()
        self.use_color = use_color and platform.system() != 'Windows'  # don't use color on windows
        msg = self.formatter_msg(self._get_format(log_name, log_pid), self.use_color)
        self._tb = TraceBack(collide=os.environ.get('DATALAD_LOGTRACEBACK', '') == 'collide') \
            if os.environ.get('DATALAD_LOGTRACEBACK', False) else None
        logging.Formatter.__init__(self, msg)

    def _get_format(self, log_name=False, log_pid=False):
        # TODO: config log.timestamp=True
        return (("" if not int(os.environ.get("DATALAD_LOG_TIMESTAMP", True)) else "$BOLD%(asctime)-15s$RESET ") +
                ("%(name)-15s " if log_name else "") +
                ("{%(process)d}" if log_pid else "") +
                "[%(levelname)s] "
                "%(message)s "
                "($BOLD%(filename)s$RESET:%(lineno)d)")

    def formatter_msg(self, fmt, use_color=False):
        if use_color:
            fmt = fmt.replace("$RESET", self.RESET_SEQ).replace("$BOLD", self.BOLD_SEQ)
        else:
            fmt = fmt.replace("$RESET", "").replace("$BOLD", "")
        return fmt

    def format(self, record):
        if record.msg.startswith('| '):
            # If we already log smth which supposed to go without formatting, like
            # output for running a command, just return the message and be done
            return record.msg

        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            fore_color = 30 + self.COLORS[levelname]
            levelname_color = self.COLOR_SEQ % fore_color + "%-7s" % levelname + self.RESET_SEQ
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

    def _get_environ(self, var, default=None):
        return os.environ.get(self.name.upper() + '_%s' % var.upper(), default)

    def set_level(self, level=None, default='WARNING'):
        """Helper to set loglevel for an arbitrary logger

        By default operates for 'datalad'.
        TODO: deduce name from upper module name so it could be reused without changes
        """
        if level is None:
            # see if nothing in the environment
            level = self._get_environ('LOGLEVEL')
        if level is None:
            level = default

        try:
            # it might be a string which still represents an int
            log_level = int(level)
        except ValueError:
            # or a string which corresponds to a constant;)
            log_level = getattr(logging, level.upper())

        self.lgr.setLevel(log_level)


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
        logtarget = self._get_environ('LOGTARGET', logtarget or 'stderr')

        # Allow for multiple handlers being specified, comma-separated
        if ',' in logtarget:
            for handler_ in logtarget.split(','):
                self.get_initialized_logger(logtarget=handler_)
            return self.lgr

        if logtarget.lower() in ('stdout', 'stderr') :
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
        # But now improve with colors and useful information such as time
        loghandler.setFormatter(
            ColorFormatter(use_color=use_color,
                           # TODO: config log.name, pid
                           log_name=self._get_environ("LOGNAME", False),
                           log_pid=self._get_environ("LOGPID", False),
                           ))
        #  logging.Formatter('%(asctime)-15s %(levelname)-6s %(message)s'))
        self.lgr.addHandler(loghandler)

        self.set_level()  # set default logging level
        return self.lgr

lgr = LoggerHelper().get_initialized_logger()

