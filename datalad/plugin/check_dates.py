import warnings

warnings.warn(
    "datalad.plugin.check_dates is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.check_dates instead.",
    DeprecationWarning)

from datalad.local.check_dates import *
