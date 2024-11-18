"""DataLad command line interface"""

# ATTN!
# The rest of the code base MUST NOT import from datalad.cli
# in order to preserve the strict separation of the CLI from the
# rest.

__docformat__ = 'restructuredtext'

import logging

lgr = logging.getLogger('datalad.cli')
