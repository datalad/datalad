# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os

from ...cmd import Runner
from ..base import AnnexExchangeProtocol


def _get_custom_runner(d):
    """A helper returning a Runner to be used in the tests for custom special remotes
    """
    # We could just propagate current environ I guess to versatile our testing
    env = os.environ.copy()
    env.update({'DATALAD_LOG_TARGET': d + '_custom.log'})
    if os.environ.get('DATALAD_LOG_LEVEL'):
        env['DATALAD_LOG_LEVEL'] = os.environ.get('DATALAD_LOG_LEVEL')
    if os.environ.get('DATALAD_TESTS_PROTOCOLREMOTE'):  # TODO config tests.customremotes.protocol
        protocol = AnnexExchangeProtocol(d, 'archive')
    else:
        protocol = None
    return Runner(cwd=d, env=env, protocol=protocol)
