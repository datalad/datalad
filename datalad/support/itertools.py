# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Auxiliary itertools"""

import itertools


def groupby_sorted(iter, key=None):
    """A little helper which first sorts iterable by the same key

    Since groupby expects sorted entries
    """
    yield from itertools.groupby(sorted(iter, key=key), key=key)
