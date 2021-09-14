import warnings

warnings.warn(
    "datalad.plugin.no_annex is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.no_annex instead.",
    DeprecationWarning)

from datalad.local.no_annex import *
