# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Crawling of external resources (e.g. websites) to get/update datasets

"""

__docformat__ = 'restructuredtext'


try:
    # TEMP: Just to overcome problem with testing on jessie with older requests
    # https://github.com/kevin1024/vcrpy/issues/215
    import vcr.patch as _vcrp
    import requests as _
    try:
        from requests.packages.urllib3.connectionpool import HTTPConnection as _a, VerifiedHTTPSConnection as _b
    except ImportError:
        def returnnothing(*args, **kwargs):
            return()
        _vcrp.CassettePatcherBuilder._requests = returnnothing
except ImportError:
    pass