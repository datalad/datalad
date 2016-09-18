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

import logging
from glob import glob
from os.path import join as opj, basename, dirname

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset

from datalad.interface.base import Interface

lgr = logging.getLogger('datalad.export')


def _get_exporter_names():
    basepath = dirname(__file__)
    return [basename(e)[:-3]
            for e in glob(opj(basepath, '*.py'))
            if not e.endswith('__init__.py')]


class Export(Interface):
    """Export a dataset to another representation
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to export. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        astype=Parameter(
            args=("astype",),
            metavar='TYPE',
            choices=_get_exporter_names(),
            doc="""label of the type or format the dataset shall be exported
            to."""),
    )

    @staticmethod
    @datasetmethod(name='export')
    def __call__(dataset, astype, **kwargs):
        # TODO
        # returns results
        pass

    @staticmethod
    def result_renderer_cmdline(res, args):
        # TODO call exporter function (if any)
