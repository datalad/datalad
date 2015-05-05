# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test command call protocols

Note: DryRunProtocol is already (kind of) tested within test_cmd.py
"""

import os
from nose.tools import ok_, eq_, assert_is, assert_equal, assert_greater, \
    assert_raises, assert_in, assert_is_instance

from ..support.protocol import DryRunProtocol, DryRunExternalsProtocol, \
    NullProtocol, ExecutionTimeProtocol, ExecutionTimeExternalsProtocol, \
    ProtocolInterface
from ..support.gitrepo import GitRepo
from ..cmd import Runner
from .utils import with_tempfile


@with_tempfile
@with_tempfile
def test_ExecutionTimeProtocol(path1, path2):

    timer_protocol = ExecutionTimeProtocol()
    runner = Runner(protocol=timer_protocol)

    # test external command:
    cmd = ['git', 'init']
    os.mkdir(path1)
    runner.run(cmd, cwd=path1)
    assert_equal(len(timer_protocol), 1, str(runner.protocol))
    assert_equal(cmd, timer_protocol[0]['command'])
    assert_greater(timer_protocol[0]['end'], timer_protocol[0]['start'])
    assert_greater(timer_protocol[0]['duration'], 0)
    assert_is(timer_protocol[0]['exception'], None)

    # now with exception, since path2 doesn't exist yet:
    try:
        runner.run(cmd, cwd=path2)
    except Exception, e:
        catched_exception = e
    finally:
        assert_equal(len(timer_protocol), 2)
        assert_equal(cmd, timer_protocol[1]['command'])
        assert_greater(timer_protocol[1]['end'], timer_protocol[1]['start'])
        assert_greater(timer_protocol[1]['duration'], 0)
        assert_is(timer_protocol[1]['exception'], catched_exception)

    # test callable:
    new_runner = Runner(cwd=path2, protocol=timer_protocol)
    git_repo = GitRepo(path2, runner=new_runner)
    assert_equal(len(timer_protocol), 3)
    assert_in('init', timer_protocol[2]['command'][0])
    assert_in('git.repo.base.Repo', timer_protocol[2]['command'][0])
    assert_in("args=('%s'" % path2, timer_protocol[2]['command'][1])
    assert_in("kwargs={}", timer_protocol[2]['command'][2])
    assert_greater(timer_protocol[2]['end'], timer_protocol[2]['start'])
    assert_greater(timer_protocol[2]['duration'], 0)



@with_tempfile
def test_protocol_commons(protocol_file):

    for protocol_class in [DryRunProtocol, DryRunExternalsProtocol,
                           ExecutionTimeExternalsProtocol, NullProtocol]:
        protocol = protocol_class()
        assert_is_instance(protocol, ProtocolInterface)

        protocol.add_section(['some_command', 'some_option'],
                             Exception("Whatever exception"))
        protocol.add_section(['another_command'], None)

        # test iterable:
        assert_raises(AssertionError, assert_raises, TypeError, iter,
                      protocol)
        for section in protocol:
            assert_in('command', section)
        for item in range(len(protocol)):
            assert_is_instance(protocol.__getitem__(item), dict)

        # test __str__:
        str_ = str(protocol)

        # test write_to_file:
        protocol.write_to_file(protocol_file)
        read_str = ''
        with open(protocol_file, 'r') as f:
            for line in f.readlines():
                read_str += line
        assert_equal(str_, read_str)
