
# handle this dance once, and import pathlib from here
# in all other places
try:
    from pathlib import (
        Path,
        PurePosixPath,
    )
except ImportError:
    from pathlib2 import (
        Path,
        PurePosixPath,
    )


def nothere(*args, **kwargs):
    raise NotImplementedError
