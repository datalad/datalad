import warnings

warnings.warn(
    "datalad.plugin.add_readme is deprecated and will be removed in a future "
    "release. "
    "Use the module from its new location datalad.local.add_readme instead.",
    DeprecationWarning)

from datalad.local.add_readme import *
