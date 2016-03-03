# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test command call protocols

Note: DryRunProtocol and NullProtocol are already (kind of) tested within
      test_cmd.py
"""

import os
from os.path import normpath
from nose.tools import ok_, eq_, assert_is, assert_equal, assert_greater, \
    assert_raises, assert_in, assert_is_instance, assert_true, assert_false

from ..support.protocol import DryRunProtocol, DryRunExternalsProtocol, \
    NullProtocol, ExecutionTimeProtocol, ExecutionTimeExternalsProtocol, \
    ProtocolInterface
from ..support.gitrepo import GitRepo
from ..cmd import Runner
from .utils import with_tempfile
from .utils import swallow_logs


@with_tempfile
def test_protocol_commons(protocol_file):

    for protocol_class in [DryRunProtocol, DryRunExternalsProtocol,
                           ExecutionTimeProtocol,
                           ExecutionTimeExternalsProtocol, NullProtocol]:
        protocol = protocol_class()
        assert_is_instance(protocol, ProtocolInterface)
        assert_equal(len(protocol), 0)

        protocol.add_section(['some_command', 'some_option'],
                             Exception("Whatever exception"))
        protocol.add_section(['another_command'], None)
        assert_equal(len(protocol), 2 if protocol_class != NullProtocol else 0)

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
    ok_(timer_protocol[0]['end'] >= timer_protocol[0]['start'])
    ok_(timer_protocol[0]['duration'] >= 0)
    assert_is(timer_protocol[0]['exception'], None)

    # now with exception, since path2 doesn't exist yet:
    try:
        with swallow_logs() as cml:
            runner.run(cmd, cwd=path2)
    except Exception as e:
        catched_exception = e
    finally:
        assert_equal(len(timer_protocol), 2)
        assert_equal(cmd, timer_protocol[1]['command'])
        ok_(timer_protocol[1]['end'] >= timer_protocol[1]['start'])
        ok_(timer_protocol[1]['duration'] >= 0)
        assert_is(timer_protocol[1]['exception'], catched_exception)

    # test callable:
    new_runner = Runner(cwd=path2, protocol=timer_protocol)
    git_repo = GitRepo(path2, runner=new_runner)
    assert_equal(len(timer_protocol), 3)
    assert_in('init', timer_protocol[2]['command'][0])
    assert_in('git.repo.base.Repo', timer_protocol[2]['command'][0])

    # extract path from args and compare
    # note: simple string concatenation for comparison doesn't work
    # on windows due to path conversion taking place
    ok_(timer_protocol[2]['command'][1].startswith("args=('"))
    extracted_path = timer_protocol[2]['command'][1].split(',')[0][7:-1]
    assert_equal(normpath(extracted_path), normpath(path2))

    assert_in("kwargs={'odbt': <class 'git.db.GitCmdObjectDB'>}", timer_protocol[2]['command'][2])
    ok_(timer_protocol[2]['end'] >= timer_protocol[2]['start'])
    ok_(timer_protocol[2]['duration'] >= 0)


@with_tempfile
@with_tempfile
def test_ExecutionTimeExternalsProtocol(path1, path2):

    timer_protocol = ExecutionTimeExternalsProtocol()
    runner = Runner(protocol=timer_protocol)

    # test external command:
    cmd = ['git', 'init']
    os.mkdir(path1)
    runner.run(cmd, cwd=path1)
    assert_equal(len(timer_protocol), 1, str(runner.protocol))
    assert_equal(cmd, timer_protocol[0]['command'])
    ok_(timer_protocol[0]['end'] >= timer_protocol[0]['start'])
    ok_(timer_protocol[0]['duration'] >= 0)
    assert_is(timer_protocol[0]['exception'], None)

    # now with exception, since path2 doesn't exist yet:
    try:
        with swallow_logs() as cml:
            runner.run(cmd, cwd=path2)
    except Exception as e:
        catched_exception = e
    finally:
        assert_equal(len(timer_protocol), 2)
        assert_equal(cmd, timer_protocol[1]['command'])
        ok_(timer_protocol[1]['end'] >= timer_protocol[1]['start'])
        ok_(timer_protocol[1]['duration'] >= 0)
        assert_is(timer_protocol[1]['exception'], catched_exception)

    # test callable (no entry added):
    new_runner = Runner(cwd=path2, protocol=timer_protocol)
    git_repo = GitRepo(path2, runner=new_runner)
    assert_equal(len(timer_protocol), 2)


@with_tempfile
def test_DryRunProtocol(path):

    protocol = DryRunProtocol()
    runner = Runner(protocol=protocol, cwd=path)
    cmd = ['git', 'init']

    # path doesn't exist, so an actual run would raise Exception,
    # but a dry run wouldn't:
    with swallow_logs() as cml:
        assert_raises(AssertionError, assert_raises, Exception, runner.run, cmd)
    assert_equal(len(protocol), 1)

    # callable is also not executed, but recorded in the protocol:
    git_repo = GitRepo(path, runner=runner)
    assert_false(os.path.exists(path))
    assert_false(os.path.exists(os.path.join(path, '.git')))
    assert_equal(len(protocol), 2)


@with_tempfile
def test_DryRunExternalsProtocol(path):

    protocol = DryRunExternalsProtocol()
    runner = Runner(protocol=protocol, cwd=path)
    cmd = ['git', 'init']

    # path doesn't exist, so an actual run would raise Exception,
    # but a dry run wouldn't:
    assert_raises(AssertionError, assert_raises, Exception, runner.run, cmd)
    assert_equal(len(protocol), 1)

    # callable is executed and not recorded in the protocol:
    git_repo = GitRepo(path, runner=runner)
    assert_true(os.path.exists(path))
    assert_true(os.path.exists(os.path.join(path, '.git')))
    assert_equal(len(protocol), 1)