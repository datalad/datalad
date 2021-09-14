import warnings

warnings.warn(
    "datalad.plugin.wtf is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.wtf instead.",
    DeprecationWarning)

from datalad.local.wtf import *
