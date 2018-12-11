from six import PY2

# handle this dance once, and import pathlib from here
# in all other places
if PY2:
    from pathlib2 import (
        Path,
        PurePosixPath,
    )
else:
    from pathlib import (
        Path,
        PurePosixPath,
    )


def nothere(*args, **kwargs):
    raise NotImplementedError
