import sys


def py2cmd(code: str,
           *additional_arguments):
    """Helper to invoke some Python code through a cmdline invocation of
    the Python interpreter.

    This should be more portable in some cases.
    """
    return [sys.executable, '-c', code] + list(additional_arguments)
