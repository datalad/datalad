# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper to deal with lzma module
"""
from __future__ import absolute_import

from six import PY2
from ..log import lgr

exc1 = ''
try:
    try:
        import lzma
    except ImportError as exc1:
        import backports.lzma as lzma
except Exception as exc2:
    if PY2 and 'undefined symbol: lzma_alone_encoder' in str(exc1):
        lgr.error(
            "lzma fails to import and a typical problem is installation "
            "of pyliblzma via pip while pkg-config utility is missing. "
            "If you did installed it using pip, please "
            "1) pip uninstall pyliblzma; "
            "2) install pkg-config (e.g. apt-get install pkg-config on "
            "Debian-based systems); "
            "3) pip install pyliblzma again.")
    raise
