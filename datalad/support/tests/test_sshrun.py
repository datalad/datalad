# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
from io import StringIO
from datalad.tests.utils import assert_raises, assert_equal

from unittest.mock import patch

from datalad.api import sshrun
from datalad.cmd import (
    StdOutCapture,
    WitlessRunner,
)
from datalad.cmdline.main import main

from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import SkipTest
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import with_tempfile


@skip_if_on_windows
@skip_ssh
def test_exit_code():
    # will relay actual exit code on CommandError
    cmd = ['datalad', 'sshrun', 'datalad-test', 'exit 42']
    with assert_raises(SystemExit) as cme:
        # running nosetests without -s
        if isinstance(sys.stdout, StringIO):  # pragma: no cover
            with swallow_outputs():  # need to give smth with .fileno ;)
                main(cmd)
        else:
            # to test both scenarios
            main(cmd)
    assert_equal(cme.exception.code, 42)


@skip_if_on_windows
@skip_ssh
@with_tempfile(content="123magic")
def test_no_stdin_swallow(fname):
    # will relay actual exit code on CommandError
    cmd = ['datalad', 'sshrun', 'datalad-test', 'cat']

    out = WitlessRunner().run(
        cmd, stdin=open(fname), protocol=StdOutCapture)
    assert_equal(out['stdout'].rstrip(), '123magic')

    # test with -n switch now, which we could place even at the end
    out = WitlessRunner().run(
        cmd + ['-n'], stdin=open(fname), protocol=StdOutCapture)
    assert_equal(out['stdout'], '')


@skip_if_on_windows
@skip_ssh
@with_tempfile(suffix="1 space", content="magic")
def test_fancy_quotes(f):
    cmd = ['datalad', 'sshrun', 'datalad-test', """'cat '"'"'%s'"'"''""" % f]
    out = WitlessRunner().run(cmd, protocol=StdOutCapture)
    assert_equal(out['stdout'], 'magic')


@skip_if_on_windows
@skip_ssh
def test_ssh_option():
    # This test is hacky in that detecting the sent value depends on systems
    # commonly configuring `AcceptEnv LC_*` in their sshd_config. If we get
    # back an empty value, assume that isn't configured, and skip the test.
    with patch.dict('os.environ', {"LC_DATALAD_HACK": 'hackbert'}):
        with swallow_outputs() as cmo:
            main(["datalad", "sshrun", "-oSendEnv=LC_DATALAD_HACK",
                  "datalad-test", "echo $LC_DATALAD_HACK"])
            out = cmo.out.strip()
            if not out:
                raise SkipTest(
                    "SSH target probably does not accept LC_* variables. "
                    "Skipping")
            assert_equal(out, "hackbert")


@skip_if_on_windows
@skip_ssh
def test_ssh_ipv4_6_incompatible():
    with assert_raises(SystemExit):
        main(["datalad", "sshrun", "-4", "-6", "datalad-test", "true"])


@skip_if_on_windows
@skip_ssh
def test_ssh_ipv4_6():
    # This should fail with a RuntimeError if a version is not supported (we're
    # not bothering to check what datalad-test supports), but if the processing
    # fails, it should be something else.
    for kwds in [{"ipv4": True}, {"ipv6": True}]:
        try:
            sshrun("datalad-test", "true", **kwds)
        except RuntimeError:
            pass
