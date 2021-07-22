#!/usr/bin/env python
"""
Check which test did not come back to initial directory and fail right away
when detected.

Could be used as easy as replacement of `python -m nose ...`, with
`python checkpwd.py --with-checkpwd ...`
"""

import os
from os import path as op
import logging
from nose.plugins.base import Plugin
from nose.util import src, tolist

log = logging.getLogger(__name__)


def getpwd():
    """Try to return a CWD without dereferencing possible symlinks

    If no PWD found in the env, output of getcwd() is returned
    """
    cwd = os.getcwd()
    try:
        env_pwd = os.environ['PWD']
        from datalad.utils import Path
        if Path(env_pwd).resolve() != Path(cwd).resolve():
            # uses os.chdir directly, pwd is not updated
            # could be an option to fail (tp not allow direct chdir)
            return cwd
        return env_pwd
    except KeyError:
        return cwd


class CheckPWD(Plugin):
    """
    Activate a coverage report using Ned Batchelder's coverage module.
    """
    name = 'checkpwd'

    def options(self, parser, env):
        """
        Add options to command line.
        """
        # throw_exception = True
        super(CheckPWD, self).options(parser, env)

    def configure(self, options, conf):
        """
        Configure plugin.
        """
        super(CheckPWD, self).configure(options, conf)
        self._pwd = getpwd()
        print("Initial PWD: %s" % self._pwd)

    def beforeTest(self, *args, **kwargs):
        """
        Begin recording coverage information.
        """
        assert getpwd() == self._pwd

    def afterTest(self, *args, **kwargs):
        """
        Stop recording coverage information.
        """
        pwd = getpwd()
        # print("Checking %s" % pwd)
        print("PWD: %s" % pwd)
        assert pwd == self._pwd, \
            "PWD original:%s  current: %s (after %s)" \
            % (self._pwd, pwd, args[0])


def test_ok():
    pass


def test_fail():
    os.chdir('/dev')


def test_fail_not_again():
    # will never reach here if test_fail fails
    pass


if __name__ == '__main__':
    import nose
    nose.main(addplugins=[CheckPWD()])
