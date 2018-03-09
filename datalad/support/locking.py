import fasteners
import os

from contextlib import contextmanager


def _get(entry):
    """A helper to ge the value, be it a callable or callable with args, or value

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
    **kwargs
):
    """A context manager to establish a lock conditionally on a check
    function result

    It is intended to be used to lock for a specific file and/or operation, e.g.
    for `annex get`ing a file or extracting an archive, so only one process
    would be performing such an operation.

    If verification of the check fails, it tries to acquire the lock, but if
    that fails on the first try, it will rerun check before proceeding to func

    checker and lock_path_prefix could be a value, or callable, or
    a tuple composing callable and its args

    Unfortunately yoh did not find any way (in Python 2) to have context manager
    which just skips the entire block if some condition is met (in python3 there
    ExitStack which could potentially be used.  So we would need still to check
    in the block body context manager return value is not None.

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
    **kwargs
      Passed to `.acquire` of the fasteners.InterProcessLock

    Returns
    -------
    result of check, lock
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

    # could use with!
    lock = fasteners.InterProcessLock(lock_filename)
    try:
        lock.acquire(blocking=blocking, **kwargs)
        if blocking:
            assert lock.acquired
        check2 = _get(check)
        if check2:
            yield check2, None
        else:
            yield check2, lock
    finally:
        if lock.acquired:
            if os.path.exists(lock_filename):
                os.unlink(lock_filename)
            lock.release()


def call_locked_if_check_fails(
        callable,
        check,
        lock_path,
        operation=None,
        **kwargs
):
    """A helper to establish a lock conditionally on a check function result

    If verification of the check fails, it tries to acquire the lock, but if
    that fails on the first try, it will rerun check before proceeding to func

    callable, checked, and lock_path_prefix could be a value, or callable, or
    a tuple composing callable and its args

    Parameters
    ----------
    callable


    Returns
    -------
    result of callable
    """
    with lock_if_check_fails(
            check,
            lock_path=lock_path,
            operation=operation,
            **kwargs
    ) as lock:
        if lock:
            return _get(callable)



