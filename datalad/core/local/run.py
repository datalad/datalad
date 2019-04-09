# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Temporary rev-run -> run alias"""

__docformat__ = 'restructuredtext'

from datalad.interface.run import (
    Run as _Run,
    run_command,
    build_doc,
    eval_results,
    _save_outputs,
)
from datalad.distribution.dataset import (
    datasetmethod,
)


@build_doc
class Run(_Run):
    __doc__ = _Run.__doc__

    @staticmethod
    @datasetmethod(name='rev_run')
    @eval_results
    def __call__(
            cmd=None,
            dataset=None,
            inputs=None,
            outputs=None,
            expand=None,
            explicit=False,
            message=None,
            sidecar=None):
        for r in run_command(cmd, dataset=dataset,
                             inputs=inputs, outputs=outputs,
                             expand=expand,
                             explicit=explicit,
                             message=message,
                             sidecar=sidecar,
                             saver=_save_outputs):
            yield r
