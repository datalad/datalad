#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
import os
import os.path as op
import sys
from pathlib import Path
from time import time

from fasteners import InterProcessLock

from datalad.tests.utils_pytest import (
    assert_false,
    assert_greater,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_true,
    eq_,
    ok_,
    ok_exists,
    on_osx,
    with_tempfile,
)

from ...cmd import (
    CommandError,
    StdOutErrCapture,
    WitlessRunner,
)
from ...utils import ensure_unicode
from ..locking import (
    lock_if_check_fails,
    try_lock_informatively,
)


class Subproc:
    # By implementing this closure as a class instead of as a nested function,
    # it becomes possible to pickle it.

    def __init__(self, tempfile):
        self.tempfile = tempfile

    def __call__(self, q):
        with lock_if_check_fails(False, self.tempfile, blocking=False, _return_acquired=True)\
                as (_, lock2, acquired):
            # we used to check for .acquired here but it was removed from
            # fasteners API: https://github.com/harlowja/fasteners/issues/71
            q.put(acquired)


@with_tempfile
def test_lock_if_check_fails(tempfile=None):
    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(True, None) as (check, lock):
        assert check is True
        assert lock is None
    assert check  # still available outside
    # and with a callable
    with lock_if_check_fails(lambda: "valuable", None) as (check, lock):
        eq_(check, "valuable")
        assert lock is None
    eq_(check, "valuable")

    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(False, tempfile) as (check, lock):
        ok_(lock)
        ok_exists(tempfile + '.lck')
    assert not op.exists(tempfile + '.lck')  # and it gets removed after

    # the same with providing operation
    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(False, tempfile, operation='get') as (check, lock):
        ok_(lock)
        ok_exists(tempfile + '.get-lck')
    assert not op.exists(tempfile + '.get-lck')  # and it gets removed after

    from multiprocessing import (
        Process,
        Queue,
    )
    q = Queue()
    p = Process(target=Subproc(tempfile), args=(q,))

    # now we need somehow to actually check the bloody lock functioning
    with lock_if_check_fails((op.exists, (tempfile,)), tempfile, _return_acquired=True) as (check, lock, acquired):
        eq_(check, False)
        ok_(lock)
        ok_(acquired)
        # but now we will try to lock again, but we need to do it in another
        # process
        p.start()
        assert q.get() is False
        p.join()
        with open(tempfile, 'w') as f:
            pass
        ok_exists(tempfile)
    ok_exists(tempfile)

    # and we redo -- it will acquire it
    p = Process(target=Subproc(tempfile), args=(q,))
    p.start()
    ok_(q.get())
    p.join()


@with_tempfile
def test_try_lock_informatively(tempfile=None):
    lock = InterProcessLock(tempfile + '.lck')
    lock_path = ensure_unicode(lock.path)  # can be bytes, complicates string formattingetc
    t0 = time()
    with try_lock_informatively(lock, purpose="happy life") as acquired:
        assert_true(lock.acquired)
        assert_true(acquired)
        assert_greater(2, time() - t0)  # should not take any notable time, we cannot be blocking

        """
        # InterProcessLock is not re-entrant so nesting should not be used, will result
        # in exception on release
        with try_lock_informatively(lock, timeouts=[dt, dt*2], proceed_unlocked=True) as acquired:
            assert_true(lock.acquired)  # due to outer cm
            assert_true(acquired)       # lock is reentrant apparently
        """
        # Let's try in a completely different subprocess
        runner = WitlessRunner(env=dict(os.environ, DATALAD_LOG_LEVEL='info', DATALAD_LOG_TARGET='stderr'))

        script1 = Path(tempfile + "-script1.py")
        script1_fmt = f"""
from fasteners import InterProcessLock
from time import time

from datalad.support.locking import try_lock_informatively

lock = InterProcessLock({lock_path!r})

with try_lock_informatively(lock, timeouts=[0.05, 0.15], proceed_unlocked={{proceed_unlocked}}) as acquired:
    print("Lock acquired=%s" % acquired)
"""
        script1.write_text(script1_fmt.format(proceed_unlocked=True))
        t0 = time()
        res = runner.run([sys.executable, str(script1)], protocol=StdOutErrCapture)
        assert_in('Lock acquired=False', res['stdout'])
        assert_in(f'Failed to acquire lock at {lock_path} in 0.05', res['stderr'])
        assert_in(f'Failed to acquire lock at {lock_path} in 0.15', res['stderr'])
        assert_in('proceed without locking', res['stderr'])
        assert_greater(time() - t0, 0.19999)  # should wait for at least 0.2
        try:
            import psutil

            # PID does not correspond
            assert_in('Check following process: PID=', res['stderr'])
            assert_in(f'CWD={os.getcwd()} CMDLINE=', res['stderr'])
        except ImportError:
            pass  # psutil was not installed, cannot get list of files
        except AssertionError:
            # we must have had the other one then
            assert_in('failed to determine one', res['stderr'])
            if not on_osx:
                # so far we had only OSX reporting failing to get PIDs information
                # but if it is something else -- re-raise original exception
                raise

        # in 2nd case, lets try without proceeding unlocked
        script1.write_text(script1_fmt.format(proceed_unlocked=False))
        t0 = time()
        with assert_raises(CommandError) as cme:
            runner.run([sys.executable, str(script1)], protocol=StdOutErrCapture)
        assert_in(f"Failed to acquire lock at {lock_path} in 2 attempts.", str(cme.value))
        assert_in(f"RuntimeError", str(cme.value))
        assert_false(cme.value.stdout)  # nothing there since print should not happen
        assert_in(f'Failed to acquire lock at {lock_path} in 0.05', cme.value.stderr)
        assert_in(f'Failed to acquire lock at {lock_path} in 0.15', cme.value.stderr)
        assert_greater(time() - t0, 0.19999)  # should wait for at least 0.2

    # now that we left context, should work out just fine
    res = runner.run([sys.executable, str(script1)], protocol=StdOutErrCapture)
    assert_in('Lock acquired=True', res['stdout'])
    assert_not_in(f'Failed to acquire lock', res['stderr'])
    assert_not_in('PID', res['stderr'])
