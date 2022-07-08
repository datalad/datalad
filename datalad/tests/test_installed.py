# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test invocation of datalad utilities "as is installed"
"""

import os
from unittest.mock import patch

from datalad.cmd import (
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.support.exceptions import CommandError
from datalad.tests.utils_pytest import (
    assert_cwd_unchanged,
    eq_,
    ok_startswith,
)


def check_run_and_get_output(cmd):
    runner = WitlessRunner()
    try:
        # suppress log output happen it was set to high values
        with patch.dict('os.environ', {'DATALAD_LOG_LEVEL': 'WARN'}):
            output = runner.run(
                ["datalad", "--help"],
                protocol=StdOutErrCapture)
    except CommandError as e:
        raise AssertionError("'datalad --help' failed to start normally. "
                             "Exited with %d and output %s" % (e.code, (e.stdout, e.stderr)))
    return output['stdout'], output['stderr']


@assert_cwd_unchanged
def test_run_datalad_help():
    out, err = check_run_and_get_output("datalad --help")
    ok_startswith(out, "Usage: ")
    # There could be a warning from coverage that no data was collected, should be benign
    lines = [l for l in err.split(os.linesep) if ('no-data-collected' not in l) and l]
    eq_(lines, [])
