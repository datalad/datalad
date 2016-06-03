# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset creation

"""

__docformat__ = 'restructuredtext'

import logging
from datalad.distribution.dataset import Dataset, datasetmethod
from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.param import Parameter

lgr = logging.getLogger('datalad.distribution.install')


class Create(Interface):
    """Create a new dataset.

    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""path where the dataset shall be  created. If `None`,
            a dataset will be created in the current working directory.
            """,
            nargs="*",
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    @datasetmethod(name='create')
    def __call__(path=None):
        raise NotImplementedError
