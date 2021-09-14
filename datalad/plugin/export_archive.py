import warnings

warnings.warn(
    "datalad.plugin.export_archive is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.export_archive instead.",
    DeprecationWarning)

from datalad.local.export_archive import *
