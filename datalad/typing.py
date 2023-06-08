# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
import typing
from typing import TypeVar

if sys.version_info >= (3, 11):
    from typing import Self
else:
    # needs typing_extensions >= 4
    # from typing_extensions import Self

    # to make packagers life easier - just duplicating verbatim
    @typing._SpecialForm
    def Self(self, params):
        """Used to spell the type of "self" in classes.

        Example::

          from typing import Self

          class ReturnsSelf:
              def parse(self, data: bytes) -> Self:
                  ...
                  return self

        """

        raise TypeError(f"{self} is not subscriptable")

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
