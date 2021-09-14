import warnings

warnings.warn(
    "datalad.plugin.addurls is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.addurls instead.",
    DeprecationWarning)

from datalad.local.addurls import *
