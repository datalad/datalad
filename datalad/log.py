# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from functools import partial
import inspect
import logging
import os
import sys
import platform
import random
import logging.handlers

from os.path import basename, dirname

from collections import defaultdict

from .utils import is_interactive, optional_args
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
    if base in set(['base', '__init__', 'utils']):
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
        ftb = self._extract_stack(limit=self.limit+10)[:-2]
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


class MemoryInfo(object):
    def __init__(self):
        try:
            from psutil import Process
            process = Process(os.getpid())
            self.memory_info = process.memory_info \
                if hasattr(process, 'memory_info') \
                else process.get_memory_info
        except:
            self.memory_info = None


    def __call__(self):
        """Return utilization of virtual memory

        Generic implementation using psutil
        """
        if not self.memory_info:
            return "RSS/VMS: N/A"
        mi = self.memory_info()
        # in later versions of psutil mi is a named tuple.
        # but that is not the case on Debian squeeze with psutil 0.1.3
        rss = mi[0] / 1024
        vms = mi[1] / 1024
        vmem = (rss, vms)

        try:
            return "RSS/VMS: %d/%d kB" % vmem
        except:
            return "RSS/VMS: %s" % str(vmem)

# Recipe from http://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
# by Brandon Thomson
# Adjusted for automagic determination whether coloring is needed and
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

        self._mem = MemoryInfo() if os.environ.get('DATALAD_LOG_VMEM', '') else None
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
        # safety guard if None was provided
        if record.msg is None:
            record.msg = ""
        else:
            # to avoid our logger puking on receiving exception instances etc.
            # .getMessage, used to interpolate it, would cast it to str anyways
            # and thus not puke
            record.msg = str(record.msg)
        if record.msg.startswith('| '):
            # If we already log smth which supposed to go without formatting, like
            # output for running a command, just return the message and be done
            return record.msg

        levelname = record.levelname

        if self.use_color and levelname in colors.LOG_LEVEL_COLORS:
            record.levelname = colors.color_word(
                "{:7}".format(levelname),
                colors.LOG_LEVEL_COLORS[levelname],
                force=True)
        record.msg = record.msg.replace("\n", "\n| ")
        if self._tb:
            if not getattr(record, 'notraceback', False):
                record.msg = self._tb() + "  " + record.msg
        if self._mem:
            record.msg = "%s %s" % (self._mem(), record.msg)

        return logging.Formatter.format(self, record)


class ProgressHandler(logging.Handler):
    from datalad.ui import ui

    def __init__(self, other_handler=None):
        super(self.__class__, self).__init__()
        self._other_handler = other_handler
        self.pbars = {}

    def close(self):
        if self._other_handler:
            self._other_handler.close()
        super().close()

    def emit(self, record):
        from datalad.ui import ui
        if not hasattr(record, 'dlm_progress'):
            self._clear_all()
            self._other_handler.emit(record)
            self._refresh_all()
            return
        maint = getattr(record, 'dlm_progress_maint', None)
        if maint == 'clear':
            return self._clear_all()
        elif maint == 'refresh':
            return self._refresh_all()
        pid = getattr(record, 'dlm_progress')
        update = getattr(record, 'dlm_progress_update', None)
        # would be an actual message, not used ATM here,
        # and the record not passed to generic handler ATM
        # (filtered away by NoProgressLog)
        # so no final message is printed
        # msg = record.getMessage()
        if pid not in self.pbars:
            # this is new
            pbar = ui.get_progressbar(
                label=getattr(record, 'dlm_progress_label', ''),
                unit=getattr(record, 'dlm_progress_unit', ''),
                total=getattr(record, 'dlm_progress_total', None,),
            )
            pbar.start(initial=getattr(record, 'dlm_progress_initial', 0))
            self.pbars[pid] = pbar
        elif update is None:
            # not an update -> done
            # TODO if the other logging that is happening is less frontpage
            # we may want to actually "print" the completion message
            self.pbars.pop(pid).finish()
        else:
            # Check for an updated label.
            label = getattr(record, 'dlm_progress_label', None)
            if label is not None:
                self.pbars[pid].set_desc(label)
            # an update
            self.pbars[pid].update(
                update,
                increment=getattr(record, 'dlm_progress_increment', False),
                total=getattr(record, 'dlm_progress_total', None))

    def _refresh_all(self):
        for pb in self.pbars.values():
            pb.refresh()

    def _clear_all(self):
        # remove the progress bar
        for pb in self.pbars.values():
            pb.clear()


class NoProgressLog(logging.Filter):
    def filter(self, record):
        return not hasattr(record, 'dlm_progress')


class OnlyProgressLog(logging.Filter):
    def filter(self, record):
        return hasattr(record, 'dlm_progress')


def filter_noninteractive_progress(logger, record):
    level = getattr(record, "dlm_progress_noninteractive_level", None)
    return level is None or level >= logger.level


def log_progress(lgrcall, pid, *args, **kwargs):
    """Helper to emit a log message on the progress of some process

    Note: Whereas this helper reports on interim progress and is to be used
    programmatically, :class:`~datalad.ui.progressbars.LogProgressBar` replaces
    a progress bar with a single log message upon completion and can be chosen
    by the user (config 'datalad.ui.progressbar' set to 'log').

    Parameters
    ----------
    lgrcall : callable
      Something like lgr.debug or lgr.info
    pid : str
      Some kind of ID for the process the progress is reported on.
    *args : str
      Log message, and potential arguments
    total : int
      Max progress quantity of the process.
    label : str
      Process description. Should be very brief, goes in front of progress bar
      on the same line.
    unit : str
      Progress report unit. Should be very brief, goes after the progress bar
      on the same line.
    update : int
      To which quantity to advance the progress.
    increment : bool
      If set, `update` is interpreted as an incremental value, not absolute.
    initial : int
      If set, start value for progress bar
    noninteractive_level : int, optional
      When a level is specified here and progress is being logged
      non-interactively (i.e. without progress bars), do not log the message if
      logging is not enabled for the specified level. This is useful when you
      want all calls to be "logged" via the progress bar, but non-interactively
      showing a message at the `lgrcall` level for each step would be too much
      noise. Note that the level here only determines if the record will be
      dropped; it will still be logged at the level of `lgrcall`.
    maint : {'clear', 'refresh'}
    """
    d = dict(
        {'dlm_progress_{}'.format(n): v for n, v in kwargs.items()
         # initial progress might be zero, but not sending it further
         # would signal to destroy the progress bar, hence test for 'not None'
         if v is not None},
        dlm_progress=pid)
    lgrcall(*args, extra=d)


@optional_args
def with_result_progress(fn, label="Total", unit=" Files", log_filter=None):
    """Wrap a progress bar, with status counts, around a function.

    Parameters
    ----------
    fn : generator function
        This function should accept a collection of items as a
        positional argument and any number of keyword arguments.  After
        processing each item in the collection, it should yield a status
        dict.
    log_filter : callable, optional
        If defined, only result records for which callable evaluates to True will be
        passed to log_progress

    label, unit : str
        Passed to log.log_progress.

    Returns
    -------
    A variant of `fn` that shows a progress bar.  Note that the wrapped
    function is not a generator function; the status dicts will be
    returned as a list.
    """
    # FIXME: This emulates annexrepo.ProcessAnnexProgressIndicators.  It'd be
    # nice to rewire things so that it could be used directly.

    def count_str(count, verb, omg=False):
        if count:
            msg = "{:d} {}".format(count, verb)
            if omg:
                msg = colors.color_word(msg, colors.RED)
            return msg


    base_label = label

    def _wrap_with_result_progress_(items, *args, **kwargs):
        counts = defaultdict(int)

        pid = "%s:%s" % (fn, random.randint(0, 100000))

        label = base_label
        log_progress(lgr.info, pid,
                     "%s: starting", label,
                     total=len(items), label=label, unit=unit,
                     noninteractive_level=5)

        for res in fn(items, *args, **kwargs):
            if not (log_filter and not log_filter(res)):
                counts[res["status"]] += 1
                count_strs = (count_str(*args)
                              for args in [(counts["notneeded"], "skipped", False),
                                           (counts["error"], "failed", True)])
                if counts["notneeded"] or counts["error"]:
                    label = "{} ({})".format(
                        base_label,
                        ", ".join(filter(None, count_strs)))

                log_progress(
                    lgr.error if res["status"] == "error" else lgr.info,
                    pid,
                    "%s: processed result%s", base_label,
                    " for " + res["path"] if "path" in res else "",
                    label=label, update=1, increment=True,
                    noninteractive_level=5)
            yield res
        log_progress(lgr.info, pid, "%s: done", base_label,
                     noninteractive_level=5)

    def _wrap_with_result_progress(items, *args, **kwargs):
        return list(_wrap_with_result_progress_(items, *args, **kwargs))

    return _wrap_with_result_progress_ \
        if inspect.isgeneratorfunction(fn) \
        else _wrap_with_result_progress


def with_progress(items, lgrcall=None, label="Total", unit=" Files"):
    """Wrap a progress bar, with status counts, around an iterable.

    Parameters
    ----------
    items : some iterable
    lgrcall: callable
      Callable for logging. If not specified - lgr.info is used
    label, unit : str
        Passed to log.log_progress.

    Yields
    ------
    Items of it while displaying the progress
    """
    pid = "with_progress-%d" % random.randint(0, 100000)
    base_label = label
    if lgrcall is None:
        lgrcall = lgr.info

    label = base_label
    log_progress(lgrcall, pid,
                 "%s: starting", label,
                 total=len(items), label=label, unit=unit,
                 noninteractive_level=5)

    for item in items:
        # Since we state "processed", and actual processing might be happening
        # outside on the yielded value, we will yield before stating that
        yield item
        log_progress(
            lgrcall,
            pid,
            "%s: processed", base_label,
            label=label, update=1, increment=True,
            noninteractive_level=5)
    log_progress(lgr.info, pid, "%s: done", base_label, noninteractive_level=5)


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
        if is_interactive():
            phandler = ProgressHandler(other_handler=loghandler)
            phandler.filters.extend(loghandler.filters)
            self.lgr.addHandler(phandler)
        else:
            loghandler.addFilter(partial(filter_noninteractive_progress,
                                         self.lgr))
            self.lgr.addHandler(loghandler)

        self.set_level()  # set default logging level
        return self.lgr


lgr = LoggerHelper().get_initialized_logger()
