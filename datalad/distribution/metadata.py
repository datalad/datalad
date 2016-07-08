# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for managing metadata
"""

__docformat__ = 'restructuredtext'


from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import datasetmethod, EnsureDataset
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..log import lgr


class MetaData(Interface):
    """Manage dataset metadata.

    Datalad's native metadata for a dataset is a flat list of term/value pairs
    (similar to DataDryad). There is no limit on the number and nature of
    metadata terms, although datalad itself only understands a few terms.
    Moreover, datalad supports multiple categories or sets of metadata. This is
    useful when managing hand-curated information in addition to automatically
    extracted metadata.

    The order in which operations are executed is:

    1. Removal
    2. Replacement
    3. Addition
    4. Aggregation
    5. Query

    Metadata items and terms can be addressed in various ways:

    - by index (run `get *` to see items indexed): -> "#16"
    - by term index (run `get <someterm>` to see items indexed for this term):
      -> "dc:contributor.author#4"
    - by term/value pair: -> "dc:contributor.author#Michael"
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        add=Parameter(
            args=("--add",),
            action="append",
            nargs=2,
            metavar="VALUE",
            doc="""[PY: list of PY] term/value pair [PY: tuples PY] to be added
            to the metadata.[CMD:  This option can be given multiple times.
            CMD]"""),
        get=Parameter(
            args=("--get",),
            metavar="TERM",
            nargs='+',
            doc="""[PY: list of PY] terms to be reported from the metadata. For
            the supported syntax to address a term, see the general
            documentation"""),
        remove=Parameter(
            args=("--remove",),
            metavar="TERM",
            nargs='+',
            doc="""[PY: list of PY] terms to be reported from the metadata. For
            the supported syntax to address a term, see the general
            documentation"""),
        replace=Parameter(
            args=("--replace",),
            action="append",
            nargs=2,
            metavar="VALUE",
            doc="""[PY: list of PY] term/value pair [PY: tuples PY] identifying
            the to-be-replaced item by its term (first value), and the
            replacement value (second value).[CMD:  This option can be given
            multiple times. CMD] For the supported syntax to address a term,
            see the general documentation"""),
        category=Parameter(
            args=("--category",),
            metavar="LABEL",
            # might think of special label "all"...
            doc="""name of the metadata category to operate on."""),
        import_from=Parameter(
            args=("--import-from",),
            metavar="SCHEMALABEL",
            doc="""label of a supported metadata scheme to import metadata
            from. Any existing metadata is replaced with the imported
            information. Use in conjunction with the metadata `category`
            setting to manage multiple sets of metadata without impacting
            the main (possible hand-curated) metadata."""),
        aggregate=Parameter(
            args=("--aggregate",),
            action="store_true",
            doc="""aggregate metadata from any installed subdataset. If a
            recursion limit is set, installed subdataset exceeding this
            limit will be ignored. Aggregation honors the selected metadata
            category"""),
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='metadata')
    def __call__(dataset, add=None, get=None, remove=None, replace=None,
                 category='datalad', import_from=None, aggregate=False,
                 recursion_limit=None):
        raise NotImplementedError
