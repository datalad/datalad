# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Progress bar implementations to be used.

Should not be imported until we know that interface needs it
"""

import sys


#
# Haven't found an ideal progress bar yet, so to make things modular etc
# we will provide our interface and adapters for few popular ones
#


class ProgressBarBase(object):
    """Base class for any progress bar"""

    def __init__(self, total=None, fill_text=None, out=None, label=None, initial=0):
        self._current = initial
        self.total = total

    def refresh(self):
        """Force update"""
        pass

    def update(self, size, increment=False):
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

    def finish(self):
        pass

    def set_desc(self, value):
        pass  # to override in subclass on how to handle description


class SilentProgressBar(ProgressBarBase):
    def __init__(self, label='', fill_text=None, total=None, unit='B', out=sys.stdout):
        super(SilentProgressBar, self).__init__(total=total)


progressbars = {'silent':  SilentProgressBar}

try:
    from tqdm import tqdm
    from datalad.support.external_versions import external_versions
    from datalad.utils import updated

    class tqdmProgressBar(ProgressBarBase):
        """Adapter for tqdm.ProgressBar"""

        backend = 'tqdm'

        # TQDM behaved a bit suboptimally with older versions -- either was
        # completely resetting time/size in global pbar, or not updating
        # "slave" pbars, so we had to
        # set miniters to 1, and mininterval to 0, so it always updates
        # amd smoothing to 0 so it produces at least consistent average.
        # But even then it is somewhat flawed.
        # Newer versions seems to behave more consistently so do not require
        # those settings
        _default_pbar_params = \
            dict(smoothing=0, miniters=1, mininterval=0) \
            if external_versions['tqdm'] < '4.10.0' \
            else dict(mininterval=0)

        def __init__(self, label='', fill_text=None,
                     total=None, unit='B', out=sys.stdout, leave=False):
            super(tqdmProgressBar, self).__init__(total=total)
            self._pbar_params = updated(
                self._default_pbar_params,
                dict(desc=label, unit=unit,
                     unit_scale=True, total=total, file=out,
                     leave=leave
                     ))
            self._pbar = None

        def _create(self):
            if self._pbar is None:
                self._pbar = tqdm(**self._pbar_params)

        def update(self, size, increment=False):
            self._create()
            inc = size - self.current
            try:
                self._pbar.update(size if increment else inc)
            except ValueError:
                # Do not crash entire process because of some glitch with
                # progressbar update
                # TODO: issue a warning?
                pass
            super(tqdmProgressBar, self).update(size, increment=increment)

        def start(self):
            super(tqdmProgressBar, self).start()
            self._create()

        def refresh(self):
            super(tqdmProgressBar, self).refresh()
            # older tqdms might not have refresh yet but I think we can live
            # without it for a bit there
            if hasattr(tqdm, 'refresh'):
                self._pbar.refresh()

        def finish(self, clear=False):
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
            self.remote.progress(self.current)

progressbars['annex-remote'] = AnnexSpecialRemoteProgressBar