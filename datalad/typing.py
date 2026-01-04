# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
from typing import (
    Concatenate,
    Literal,
    ParamSpec,
    Protocol,
    TypedDict,
    TypeVar,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

__all__ = ["Literal", "ParamSpec", "T", "K", "V", "P"]

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
P = ParamSpec("P")
