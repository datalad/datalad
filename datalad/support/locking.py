import fasteners
import os

from operator import isCallable


def _get(entry):
    if isinstance(entry, (tuple, list)):
        func, args = entry
        return func(*args)
    elif isCallable(entry):
        return entry()
    else:
        return entry


def locked_call_if_not_verified(
        callable,
        checker,
        lock_path_prefix,
        operation='',
        **kwargs
):
    """A helper to establish a lock conditionally on a check function result

    If verification of the check fails, it tries to acquire the lock, but if
    that fails on the first try, it will rerun check before proceeding to func

    callable, checked, and lock_path_prefix could be a value, or callable, or
    a tuple composing callable and its args

    Parameters
    ----------
    TODO

    Returns
    -------
    result of check
    """
    check1 = _get(checker)
    if check1:  # we are done - nothing to do
        return check1

    # acquire blocking lock
    lock_filename = _get(lock_path_prefix)
    if operation:
        lock_filename += '-' + operation
    lock_filename += '.lck'

    lock = fasteners.InterProcessLock(lock_filename)
    try:
        lock.acquire(**kwargs)
        assert lock.acquired
        check2 = _get(checker)
        if check2:
            return check2  # no longer needed
        _ = _get(callable)
    finally:
        if os.path.exists(lock_filename):
            os.unlink(lock_filename)
        lock.release()
    return _get(checker)



