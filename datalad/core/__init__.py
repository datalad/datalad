# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Minimal set of commands that serve as the foundation for others.

These receive special scrutiny with regard API composition and changes.

**NOTE**

Actually, the above isn't true at the moment. But that is the plan:
<https://github.com/datalad/datalad/issues/3192>

Currently new modules that are making their way over from the
datalad-revolution are following this scheme.
"""

__docformat__ = 'restructuredtext'
