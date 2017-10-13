# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Adapters and decorators for vcr
"""

import logging

from functools import wraps
from os.path import isabs
from os.path import realpath
from contextlib import contextmanager

from datalad.dochelpers import exc_str

lgr = logging.getLogger("datalad.support.vcr")


def _get_cassette_path(path):
    """Return a path to the cassette within our unified 'storage'"""
    if not isabs(path):  # so it was given as a name
        return "fixtures/vcr_cassettes/%s.yaml" % path
    return path

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

    from vcr import use_cassette as _use_cassette, VCR as _VCR

    def use_cassette(path, return_body=None, **kwargs):
        """Adapter so we could create/use custom use_cassette with custom parameters

        Parameters
        ----------
        path : str
          If not absolute path, treated as a name for a cassette under fixtures/vcr_cassettes/
        """
        path = _get_cassette_path(path)
        lgr.debug("Using cassette %s" % path)
        if return_body is not None:
            my_vcr = _VCR(
                before_record_response=lambda r: dict(r, body={'string': return_body.encode()}))
            return my_vcr.use_cassette(path, **kwargs)  # with a custom response
        else:
            return _use_cassette(path, **kwargs)  # just a straight one

    # shush vcr
    vcr_lgr = logging.getLogger('vcr')
    if lgr.getEffectiveLevel() > logging.DEBUG:
        vcr_lgr.setLevel(logging.WARN)
except Exception as exc:
    if not isinstance(exc, ImportError):
        # something else went hairy (e.g. vcr failed to import boto due to some syntax error)
        lgr.warning("Failed to import vcr, no cassettes will be available: %s",
                    exc_str(exc, limit=10))
    # If there is no vcr.py -- provide a do nothing decorator for use_cassette

    def use_cassette(*args, **kwargs):
        def do_nothing_decorator(t):
            @wraps(t)
            def wrapper(*args, **kwargs):
                lgr.debug("Not using vcr cassette")
                return t(*args, **kwargs)
            return wrapper
        return do_nothing_decorator


@contextmanager
def externals_use_cassette(name):
    """Helper to pass instruction via env variables to use specified cassette

    For instance whenever we are testing custom special remotes invoked by the annex
    but want to minimize their network traffic by using vcr.py
    """
    from mock import patch
    cassette_path = realpath(_get_cassette_path(name))  # realpath OK
    with patch.dict('os.environ', {'DATALAD_TESTS_USECASSETTE': cassette_path}):
        yield
