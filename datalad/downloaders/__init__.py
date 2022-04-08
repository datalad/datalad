# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Sub-module to provide access (as to download/query etc) to the remote sites

"""

from datalad.downloaders.credentials import (
    AWS_S3,
    LORIS_Token,
    NDA_S3,
    Token,
    UserPassword,
    GitCredential)

__docformat__ = 'restructuredtext'

from logging import getLogger
lgr = getLogger('datalad.providers')

# TODO: we might not need to instantiate it right here
# lgr.debug("Initializing data providers credentials interface")
# providers = Providers().from_config_files()
CREDENTIAL_TYPES = {
    'user_password': UserPassword,
    'aws-s3': AWS_S3,
    'nda-s3': NDA_S3,
    'token': Token,
    'loris-token': LORIS_Token,
    'git': GitCredential,
}
