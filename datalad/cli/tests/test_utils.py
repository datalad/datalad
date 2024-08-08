import sys
from unittest.mock import patch

import pytest

from datalad.tests.utils_pytest import (
    eq_,
    ok_,
)
from datalad.utils import (
    swallow_logs,
    swallow_outputs,
)

from ..utils import setup_exceptionhook


@pytest.mark.parametrize("interactive", [True, False])
def test_setup_exceptionhook(interactive):
    old_exceptionhook = sys.excepthook

    post_mortem_tb = []

    def our_post_mortem(tb):
        post_mortem_tb.append(tb)

    with patch('sys.excepthook'), \
            patch('datalad.utils.is_interactive', lambda: interactive), \
            patch('pdb.post_mortem', our_post_mortem):
        setup_exceptionhook()
        our_exceptionhook = sys.excepthook
        ok_(old_exceptionhook != our_exceptionhook)
        with swallow_logs() as cml, swallow_outputs() as cmo:
            # we need to call our_exceptionhook explicitly b/c nose
            # swallows all Exceptions and hook never gets executed
            try:
                raise RuntimeError
            except Exception as e:  # RuntimeError:
                type_, value_, tb_ = sys.exc_info()
            our_exceptionhook(type_, value_, tb_)

    eq_(old_exceptionhook, sys.excepthook)
