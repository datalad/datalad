# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Progress bar implementations to be used.

Should not be imported until we know that interface needs it
"""

import humanize
import sys
import time

from .. import lgr

#
# Haven't found an ideal progress bar yet, so to make things modular etc
# we will provide our interface and adapters for few popular ones
#


class ProgressBarBase(object):
    """Base class for any progress bar"""

    def __init__(self, label=None, fill_text=None, total=None, out=None, unit='B'):
        self.label = label
        self.fill_text = fill_text
        self.total = total
        self.unit = unit
        self.out = out
        self._current = 0

    def refresh(self):
        """Force update"""
        pass

    def update(self, size, increment=False, total=None):
        if total:
            self.total = total
        if not size:
            return
        if increment:
            self._current += size
        else:
            self._current = size

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, value):
        assert value >= 0, "Total cannot be negative"
        self._current = value

    def start(self, initial=0):
        self._current = initial

    def finish(self, partial=False):
        """

        Parameters
        ----------
        partial: bool
          To signal that finish is called possibly before the activity properly
          finished, so .total count might have not been reached

        Returns
        -------

        """
        pass

    def clear(self):
        pass

    def set_desc(self, value):
        pass  # to override in subclass on how to handle description


class SilentProgressBar(ProgressBarBase):
    def __init__(self, label='', fill_text=None, total=None, unit='B', out=sys.stdout):
        super(SilentProgressBar, self).__init__(total=total)


class LogProgressBar(ProgressBarBase):
    """A progress bar which logs upon completion of the item

    Note that there is also :func:`~datalad.log.log_progress` which can be used
    to get progress bars when attached to a tty but incremental log messages
    otherwise (as opposed to just the final log message provided by
    `LogProgressBar`).
    """

    def __init__(self, *args, **kwargs):
        super(LogProgressBar, self).__init__(*args, **kwargs)
        # I think we never generate progress bars unless we are at the beginning
        # of reporting something lengthy.  .start is not always invoked so
        # we cannot reliably set it there instead of the constructor (here)
        self._start_time = time.time()

    @staticmethod
    def _naturalfloat(x):
        """Return string representation of a number for human consumption

        For abs(x) <= 1000 would use 'scientific' (%g) notation, and for the
        larger a regular int (after rounding)
        """
        return ('%g' % x) if abs(x) <= 1000 else '%i' % int(round(x))

    def _naturalsize(self, x):
        if self.unit == 'B':
            return humanize.naturalsize(x)
        else:
            return '%s%s' % (self._naturalfloat(x), self.unit or '')

    @staticmethod
    def _naturaldelta(x):
        # humanize is too human for little things
        return humanize.naturaldelta(x) \
            if x > 2 \
            else LogProgressBar._naturalfloat(x) + ' sec'

    def start(self, initial=0):
        super().start(initial=initial)
        msg = " with initial specified to be {initial}" if initial else ''
        lgr.info("Start %s%s", self.label, msg)

    def finish(self, partial=False):
        msg, args = ' %s ', [self.label]

        if partial:
            # that is the best we know so far:
            amount = self.current
            if self.total is not None:
                if amount != self.total:
                    perc_done = 100. * amount / self.total
                    if perc_done <= 100:
                        msg += "partially (%.2f%% of %s) "
                        args += [
                            perc_done,
                            self._naturalsize(self.total)
                        ]
                    else:
                        # well well -- we still probably have some issue with
                        # over-reporting when getting data from datalad-archives
                        # Instead of providing non-sense % here, just report
                        # our best guess
                        msg += "possibly partially "
                else:
                    # well -- that means that we did manage to get all of it
                    pass
            else:
                msg += "possibly partially "
            msg += "done"
        else:
            # Are we "finish"ed because interrupted or done?
            amount = self.total
            if amount:
                msg += '%s done'
                args += [self._naturalsize(amount)]
            else:
                msg += "done"

        dt = float(time.time() - self._start_time)

        if dt:
            msg += ' in %s'
            args += [self._naturaldelta(dt)]

            if amount:
                speed = amount / dt
                msg += ' at %s/sec'
                args += [self._naturalsize(speed)]

        lgr.info(msg, *args)


progressbars = {
    # let for compatibility, use "none" instead
    'silent':  SilentProgressBar,
    'none':  SilentProgressBar,
    'log': LogProgressBar,
}


try:
    from tqdm import tqdm
    from datalad.support.external_versions import external_versions
    from datalad.utils import updated

    class tqdmProgressBar(ProgressBarBase):
        """Adapter for tqdm.ProgressBar"""

        backend = 'tqdm'
        _frontends = {
            None: tqdm,
            'ipython': None  # to be loaded
        }

        # TQDM behaved a bit suboptimally with older versions -- either was
        # completely resetting time/size in global pbar, or not updating
        # "slave" pbars, so we had to
        # set miniters to 1, and mininterval to 0, so it always updates
        # amd smoothing to 0 so it produces at least consistent average.
        # But even then it is somewhat flawed.
        # Newer versions seems to behave more consistently so do not require
        # those settings
        _default_pbar_params = \
            dict(smoothing=0, miniters=1, mininterval=0.1) \
            if external_versions['tqdm'] < '4.10.0' \
            else dict(mininterval=0.1)

        # react to changes in the terminal width
        if external_versions['tqdm'] >= '2.1':
            _default_pbar_params['dynamic_ncols'] = True

        def __init__(self, label='', fill_text=None,
                     total=None, unit='B', out=sys.stdout, leave=False,
                     frontend=None):
            """

            Parameters
            ----------
            label
            fill_text
            total
            unit
            out
            leave
            frontend: (None, 'ipython'), optional
              tqdm module to use.  Could be tqdm_notebook if under IPython
            """
            super(tqdmProgressBar, self).__init__(label=label,
                                                  total=total,
                                                  unit=unit)

            if frontend not in self._frontends:
                raise ValueError(
                    "Know only about following tqdm frontends: %s. Got %s"
                    % (', '.join(map(str, self._frontends)),
                       frontend))

            tqdm_frontend = self._frontends[frontend]
            if not tqdm_frontend:
                if frontend == 'ipython':
                    from tqdm import tqdm_notebook
                    tqdm_frontend = self._frontends[frontend] = tqdm_notebook
                else:
                    lgr.error(
                        "Something went wrong here, using default tqdm frontend for %s",
                        frontend)
                    tqdm_frontend = self._frontends[frontend] = self._frontends[None]

            self._tqdm = tqdm_frontend
            self._pbar_params = updated(
                self._default_pbar_params,
                dict(desc=label, unit=unit,
                     unit_scale=True, total=total, file=out,
                     leave=leave,
                     ))
            if label and 'total' in label.lower() and 'smoothing' not in self._pbar_params:
                # ad-hoc: All tqdm totals will report total mean, and not some
                # momentary speed
                self._pbar_params['smoothing'] = 0
            self._pbar = None

        def _create(self, initial=0):
            if self._pbar is None:
                self._pbar = self._tqdm(initial=initial, **self._pbar_params)

        @staticmethod
        def _reset_kludge(pbar, total=None):
            # tqdm didn't have reset() until v4.32.0 (c7015f4,
            # 2019-05-10).  This code below is copied from
            # tqdm.reset() in v4.46.1, replacing "self" with "pbar".
            # It hasn't changed since added in c7015f4.
            #
            # TODO: Drop this and set a minimum tqdm version once
            # Debian stable has v4.32.0.
            pbar.last_print_n = pbar.n = 0
            pbar.last_print_t = pbar.start_t = pbar._time()
            if total is not None:
                pbar.total = total
            pbar.refresh()

        def update(self, size, increment=False, total=None):
            self._create()
            if total is not None:
                # only a reset can change the total of an existing pbar
                try:
                    self._pbar.reset(total)
                except AttributeError:
                    self._reset_kludge(self._pbar, total)
                # we need to (re-)advance the pbar back to the old state
                self._pbar.update(self.current)
                # an update() does not (reliably) trigger a refresh, hence
                # without the next, the pbar may still show zero progress
                if not size:
                    # whenever a total is changed, we need a refresh. If there is
                    # no progress update, we do it here, else we'll do it after
                    # the progress update
                    self._pbar.refresh()
                # if we set a new total and also advance the progress bar:
            if not size:
                return
            inc = size - self.current
            try:
                self._pbar.update(size if increment else inc)
                if total:
                    # refresh to new total and progress
                    self._pbar.refresh()
            except ValueError:
                # Do not crash entire process because of some glitch with
                # progressbar update
                # TODO: issue a warning?
                pass
            super(tqdmProgressBar, self).update(size,
                                                increment=increment,
                                                total=total)

        def start(self, initial=0):
            super(tqdmProgressBar, self).start(initial=initial)
            self._create(initial=initial)

        def refresh(self):
            super(tqdmProgressBar, self).refresh()
            # older tqdms might not have refresh yet but I think we can live
            # without it for a bit there
            if hasattr(self._tqdm, 'refresh'):
                self._pbar.refresh()

        def finish(self, clear=False, partial=False):
            """

            Parameters
            ----------
            clear : bool, optional
              Explicitly clear the progress bar. Note that we are
              creating them with leave=False so they should disappear on their
              own and explicit clear call should not be necessary

            Returns
            -------

            """
            if clear:
                self.clear()
            # be tolerant to bugs in those
            try:
                if self._pbar is not None:
                    self._pbar.close()
            finally:
                self._pbar = None
            try:
                super(tqdmProgressBar, self).finish()
            except Exception as exc:  # pragma: no cover
                #lgr.debug("Finishing tqdmProgresBar thrown %s", str_exc(exc))
                pass

        def clear(self):
            try:
                self._pbar.clear()
            except:
                # if has none -- we can't do anything about it for now ;)
                # 4.7.4 seems to have it
                pass

        def set_desc(self, value):
            self._pbar.desc = value


    progressbars['tqdm'] = tqdmProgressBar
except ImportError:  # pragma: no cover
    pass

assert len(progressbars), "We need tqdm library to report progress"


class AnnexSpecialRemoteProgressBar(ProgressBarBase):
    """Hook up to the special remote and report progress back to annex"""

    def __init__(self, *args, **kwargs):
        # not worth passing anything since we don't care about anything
        remote = kwargs.get('remote')
        super(AnnexSpecialRemoteProgressBar, self).__init__()
        self.remote = remote

    def update(self, *args, **kwargs):
        super(AnnexSpecialRemoteProgressBar, self).update(*args, **kwargs)
        # now use stored value
        if self.remote:
            self.remote.send_progress(self.current)

progressbars['annex-remote'] = AnnexSpecialRemoteProgressBar
