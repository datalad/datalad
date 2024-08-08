import logging
from contextlib import contextmanager

from fasteners import (
    InterProcessLock,
    try_lock,
)

from datalad.support.exceptions import CapturedException

from ..utils import (
    ensure_unicode,
    get_open_files,
    unlink,
)
from .path import exists

lgr = logging.getLogger('datalad.locking')


def _get(entry):
    """A helper to get the value, be it a callable or callable with args, or value

    """
    if isinstance(entry, (tuple, list)):
        func, args = entry
        return func(*args)
    elif callable(entry):
        return entry()
    else:
        return entry


@contextmanager
def lock_if_check_fails(
    check,
    lock_path,
    operation=None,
    blocking=True,
    _return_acquired=False,
    **kwargs
):
    """A context manager to establish a lock conditionally on result of a check

    It is intended to be used as a lock for a specific file and/or operation,
    e.g. for `annex get`ing a file or extracting an archive, so only one process
    would be performing such an operation.

    If verification of the check fails, it tries to acquire the lock, but if
    that fails on the first try, it will rerun check before proceeding to func

    checker and lock_path_prefix could be a value, or callable, or
    a tuple composing callable and its args

    Unfortunately yoh did not find any way in Python 2 to have a context manager
    which just skips the entire block if some condition is met (in Python3 there
    is ExitStack which could potentially be used).  So we would need still to
    check in the block body if the context manager return value is not None.

    Note also that the used type of the lock (fasteners.InterprocessLock) works
    only across processes and would not lock within the same (threads) process.

    Parameters
    ----------
    check: callable or (callable, args) or value
      If value (possibly after calling a callable) evaluates to True, no
      lock is acquired, and no context is executed
    lock_path: callable or (callable, args) or value
      Provides a path for the lock file, composed from that path + '.lck'
      extension
    operation: str, optional
      If provided, would be part of the locking extension
    blocking: bool, optional
      If blocking, process would be blocked until acquired and verified that it
      was acquired after it gets the lock
    _return_acquired: bool, optional
      Return also if lock was acquired.  For "private" use within DataLad (tests),
      do not rely on it in 3rd party solutions.
    **kwargs
      Passed to `.acquire` of the fasteners.InterProcessLock

    Returns
    -------
    result of check, lock[, acquired]
    """
    check1 = _get(check)
    if check1:  # we are done - nothing to do
        yield check1, None
        return
    # acquire blocking lock
    lock_filename = _get(lock_path)

    lock_filename += '.'
    if operation:
        lock_filename += operation + '-'
    lock_filename += 'lck'

    lock = InterProcessLock(lock_filename)
    acquired = False
    try:
        lgr.debug("Acquiring a lock %s", lock_filename)
        acquired = lock.acquire(blocking=blocking, **kwargs)
        lgr.debug("Acquired? lock %s: %s", lock_filename, acquired)
        if blocking:
            assert acquired
        check2 = _get(check)
        ret_lock = None if check2 else lock
        if _return_acquired:
            yield check2, ret_lock, acquired
        else:
            yield check2, ret_lock
    finally:
        if acquired:
            lgr.debug("Releasing lock %s", lock_filename)
            lock.release()
            if exists(lock_filename):
                unlink(lock_filename)


@contextmanager
def try_lock_informatively(lock, purpose=None, timeouts=(5, 60, 240), proceed_unlocked=False):
    """Try to acquire lock (while blocking) multiple times while logging INFO messages on failure

    Primary use case is for operations which are user-visible and thus should not lock
    indefinitely or for long period of times (so user would just Ctrl-C if no update is provided)
    without "feedback".

    Parameters
    ----------
    lock: fasteners._InterProcessLock
    purpose: str, optional
    timeouts: tuple or list, optional
    proceed_unlocked: bool, optional
    """
    purpose = " to " + str(purpose) if purpose else ''

    # could be bytes, making formatting trickier
    lock_path = ensure_unicode(lock.path)

    def get_pids_msg():
        try:
            pids = get_open_files(lock_path)
            if pids:
                proc = pids[lock_path]
                return f'Check following process: PID={proc.pid} CWD={proc.cwd()} CMDLINE={proc.cmdline()}.'
            else:
                return 'Stale lock? I found no processes using it.'
        except Exception as exc:
            lgr.debug(
                "Failed to get a list of processes which 'posses' the file %s: %s",
                lock_path,
                CapturedException(exc)
            )
            return 'Another process is using it (failed to determine one)?'

    lgr.debug("Acquiring a currently %s lock%s. If stalls - check which process holds %s",
              ("existing" if lock.exists() else "absent"),
              purpose,
              lock_path)

    was_locked = False  # name of var the same as of within fasteners.try_lock
    assert timeouts  # we expect non-empty timeouts
    try:
        for trial, timeout in enumerate(timeouts):
            was_locked = lock.acquire(blocking=True, timeout=timeout)
            if not was_locked:
                if trial < len(timeouts) - 1:
                    msg = " Will try again and wait for up to %4g seconds." % (timeouts[trial+1],)
                else:  # It was the last attempt
                    if proceed_unlocked:
                        msg = " Will proceed without locking."
                    else:
                        msg = ""
                lgr.info("Failed to acquire lock%s at %s in %4g seconds. %s%s",
                         purpose, lock_path, timeout, get_pids_msg(), msg)
            else:
                yield True
                return
        else:
            assert not was_locked
            if proceed_unlocked:
                yield False
            else:
                raise RuntimeError(
                    "Failed to acquire lock%s at %s in %d attempts.%s"
                    % (purpose, lock_path, len(timeouts), get_pids_msg()))
    finally:
        if was_locked:
            lock.release()
