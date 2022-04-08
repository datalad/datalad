# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### #
import sys
import json

from urllib.request import (
    Request,
    urlopen,
)
from urllib.error import HTTPError

from datalad.support.exceptions import (
    AccessDeniedError,
)
from datalad.utils import ensure_unicode


class LORISTokenGenerator(object):
    """
    Generate a LORIS API token by making a request to the
    LORIS login API endpoint with the given username
    and password.

    url is the complete URL of the $LORIS/api/$VERSION/login
    endpoint.
    """
    def __init__(self, url=None):
        assert(url is not None)
        self.url = url

    def generate_token(self, user=None, password=None):
        data = {'username': user, 'password' : password}
        encoded_data = json.dumps(data).encode('utf-8')

        request = Request(self.url, encoded_data)

        try:
            response = urlopen(request)
        except HTTPError:
            raise AccessDeniedError("Could not authenticate into LORIS")

        str_response = ensure_unicode(response.read())
        data = json.loads(str_response)
        return data["token"]

