import warnings

warnings.warn(
    "datalad.plugin.export_to_figshare is deprecated and will be removed "
    "in a future release. Use the module from its new location "
    "datalad.distributed.export_to_figshare instead.",
    DeprecationWarning)

from datalad.distributed.export_to_figshare import *
