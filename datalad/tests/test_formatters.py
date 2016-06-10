# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

from cStringIO import StringIO as SIO
import formatters as fmt
from .utils import assert_equal, ok_, assert_raises, assert_in, ok_startswith

demo_example = """
#!/bin/sh

set -e
set -u

# BOILERPLATE

HOME=IS_MY_CASTLE

#% EXAMPLE START

#% A simple start (on the command line)
#% ====================================

#% Lorem ipsum

datalad install http://the.world.com

#% Epilog -- with multiline rubish sdoifpwjefw
#% vsdokvpsokdvpsdkv spdokvpskdvpoksd
#% pfdsvja329u0fjpdsv sdpf9p93qk

datalad imagine --too \\
        --much \\
        --too say \\
        yes=no

#% The result is not comprehensible.

#% EXAMPLE END

# define shunit test cases below, or just anything desired
"""


def test_cmdline_example_to_rst():
    # don't puke on nothing
    out = fmt.cmdline_example_to_rst(SIO(''))
    out.seek(0)
    ok_startswith(out.read(), '.. AUTO-GENERATED')
    out = fmt.cmdline_example_to_rst(SIO(''), ref='dummy')
    out.seek(0)
    assert_in('.. dummy:', out.read())
    # full scale test
    out = fmt.cmdline_example_to_rst(
        SIO(demo_example), ref='mydemo')
    out.seek(0)
    assert_in('.. code-block:: sh', out.read())
