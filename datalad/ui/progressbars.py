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
    def __init__(self, maxval=None):
        self._prev_value = 0
        self.maxval = maxval

    def refresh(self):
        """Force update"""
        pass

    def update(self, size, increment=False):
        if increment:
            self._prev_value += size
        else:
            self._prev_value = size

    def start(self):
        pass

    def finish(self):
        self._prev_value = 0

progressbars = {}

try:
    from tqdm import tqdm

    class tqdmProgressBar(ProgressBarBase):
        """Adapter for tqdm.ProgressBar"""

        backend = 'tqdm'

        def __init__(self, label='', fill_text=None, maxval=None, unit='B', out=sys.stdout):
            super(tqdmProgressBar, self).__init__(maxval=maxval)
            self._pbar_params = dict(desc=label, unit=unit,
                                     unit_scale=True, total=maxval, file=out)
            self._pbar = None

        def _create(self):
            if self._pbar is None:
                # set miniters to 1, and mininterval to 0, so it always updates
                self._pbar = tqdm(miniters=1, mininterval=0, **self._pbar_params)

        def update(self, size, increment=False):
            self._create()
            inc = size - self._prev_value
            self._pbar.update(size if increment else inc)
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

        def finish(self):
            self.clear()
            # be tollerant to bugs in those
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
            self.remote.progress(self._prev_value)

progressbars['annex-remote'] = AnnexSpecialRemoteProgressBar