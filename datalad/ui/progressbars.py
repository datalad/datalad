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
    def __init__(self, maxval=None):
        self._prev_value = 0
        self.maxval = maxval

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
    from progressbar import Bar, ETA, FileTransferSpeed, \
        Percentage, ProgressBar, RotatingMarker

    # TODO: might better delegate to an arbitrary bar?
    class BarWithFillText(Bar):
        """A progress bar widget which fills the bar with the target text"""

        def __init__(self, fill_text, **kwargs):
            super(BarWithFillText, self).__init__(**kwargs)
            self.fill_text = fill_text

        def update(self, pbar, width):
            orig = super(BarWithFillText, self).update(pbar, width)
            # replace beginning with the title
            if len(self.fill_text) > width:
                # TODO:  make it fancier! That we also at the same time scroll it from
                # the left so it does end up at the end with the tail but starts with
                # the beginning
                fill_text = '...' + self.fill_text[-(width-4):]
            else:
                fill_text = self.fill_text
            fill_text = fill_text[:min(len(fill_text), int(round(width * pbar.percentage()/100.)))]
            return fill_text + " " + orig[len(fill_text)+1:]

    class progressbarProgressBar(ProgressBarBase):
        """Adapter for progressbar.ProgressBar"""

        backend = 'progressbar'

        def __init__(self, label='', fill_text=None, maxval=None, unit='B', out=sys.stdout):
            super(progressbarProgressBar, self).__init__(maxval=maxval)
            assert(unit == 'B')  # none other "supported" ATM
            bar = dict(marker=RotatingMarker())
            # TODO: RF entire messaging to be able to support multiple progressbars at once
            widgets = ['%s: ' % label,
                       BarWithFillText(fill_text=fill_text, marker=RotatingMarker()), ' ',
                       Percentage(), ' ',
                       ETA(), ' ',
                       FileTransferSpeed()]
            self._pbar = ProgressBar(widgets=widgets, maxval=maxval, fd=out).start()

        def update(self, size, increment=False):
            self._pbar.update(self._prev_value + size if increment else size)
            super(progressbarProgressBar, self).update(size, increment=increment)

        def start(self):
            super(progressbarProgressBar, self).start()
            self._pbar.start()

        def clear(self):
            pass

        def finish(self):
            if self._pbar:
                self._pbar.finish()
            super(progressbarProgressBar, self).finish()

    progressbars['progressbar'] = progressbarProgressBar
except ImportError:  # pragma: no cover
    pass

try:
    from tqdm import tqdm

    class tqdmProgressBar(ProgressBarBase):
        """Adapter for tqdm.ProgressBar"""

        backend = 'tqdm'

        def __init__(self, label='', fill_text=None, maxval=None, unit='B', out=sys.stdout):
            super(tqdmProgressBar, self).__init__(maxval=maxval)
            self._pbar_params = dict(desc=label, unit=unit, unit_scale=True, total=maxval, file=out)
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
            self._pbar.clear()


    progressbars['tqdm'] = tqdmProgressBar
except ImportError:  # pragma: no cover
    pass

assert len(progressbars), "We need tqdm or progressbar library to report progress"

