# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for running commands with `asyncio.create_subprocess_{shell,exec}`.

This is intended for internal use by `cmd.Runner`.
"""

import asyncio
from functools import partial
import locale
import logging
import sys

lgr = logging.getLogger('datalad.acmd')


async def _noop():
    return None


async def _read_stream(stream, callback):
    while True:
        line = await stream.readline()
        if line:
            callback(line)
        else:
            break


async def _run_subprocess(command, stdout_callback=None, stderr_callback=None,
                          **kwds):
    if kwds.get("shell"):
        fn = partial(asyncio.create_subprocess_shell,
                     command)
    else:
        fn = partial(asyncio.create_subprocess_exec,
                     *command)
    process = await fn(stdout=asyncio.subprocess.PIPE,
                       stderr=asyncio.subprocess.PIPE,
                       **kwds)

    if stdout_callback is not None:
        stdout = _read_stream(process.stdout, stdout_callback)
    else:
        stdout = _noop()

    if stderr_callback is not None:
        stderr = _read_stream(process.stderr, stderr_callback)
    else:
        stderr = _noop()

    await asyncio.tasks.gather(stdout, stderr)
    exit_code = await process.wait()
    return exit_code


def _write(stream, line):
    stream.buffer.write(line)
    stream.flush()


def _call_with_decoded(fn):
    encoding = locale.getpreferredencoding(False)

    def wrapped(line):
        # This decode then encode again isn't ideal, but it is done to get a
        # consistent return value and work with the existing Runner() code.
        # Eventually it'd probably be best for all the callbacks to be expected
        # to return unicode.
        res = fn(line.decode(encoding))
        return res.encode(encoding) if res else b''
    return wrapped


def _collect(container, transform_fn=None):
    if transform_fn is None:
        fn = container.append
    else:
        def fn(line):
            res = transform_fn(line)
            if res is not None:
                container.append(res)
    return fn


def run(cmd, log_stdout=True, log_stderr=True, **kwds):
    """Run a command through `asyncio.create_subprocess_{exec,shell}`.

    Parameters
    ----------
    cmd : list of str or str
        A command in the same form as accepted by `cmd.Runner`.
    log_stdout, log_stderr : bool or callable
        If a callable, it should take a line from the stream. Any value it
        returns will be captured as output for that stream. Otherwise, a true
        value results in the output for that stream being captured, while a
        false value results in the line being directly written to the stream.
    **kwds
        Keyword arguments passed to `create_subprocess_{exec,shell}` call.

    Returns
    -------
    A tuple where the first item is a tuple of (stdout, stderr) byte strings
    with captured output and the second item is the exit code of the process.
    """
    # Set up callbacks for each stream.
    captured = {}
    for name, param in [("stdout", log_stdout),
                        ("stderr", log_stderr)]:
        cb_key = "{}_callback".format(name)
        if param:
            captured[name] = []
            if callable(param):
                kwds[cb_key] = _collect(captured[name],
                                        transform_fn=_call_with_decoded(param))
            elif param:
                kwds[cb_key] = _collect(captured[name])
        else:
            kwds[cb_key] = partial(_write, getattr(sys, name))

    # Run command.
    loop = asyncio.get_event_loop()
    status = loop.run_until_complete(_run_subprocess(cmd, **kwds))
    out = tuple(b''.join(captured.get(s, b'')) for s in ["stdout", "stderr"])
    return out, status
