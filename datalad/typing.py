# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
from typing import TypeVar

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if sys.version_info >= (3, 10):
    from typing import (
        Concatenate,
        ParamSpec,
    )
else:
    from typing_extensions import (
        Concatenate,
        ParamSpec,
    )

if sys.version_info >= (3, 8):
    from typing import (
        Literal,
        Protocol,
        TypedDict,
    )
else:
    from typing_extensions import (
        Literal,
        Protocol,
        TypedDict,
    )

__all__ = ["Literal", "ParamSpec", "T", "K", "V", "P"]

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
P = ParamSpec("P")
