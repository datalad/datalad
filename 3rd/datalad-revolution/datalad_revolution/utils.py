from six import PY2
import datalad.support.ansi_colors as ac

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


state_color_map = {
    'untracked': ac.RED,
    'modified': ac.RED,
    'added': ac.GREEN,
}


def nothere(*args, **kwargs):
    raise NotImplementedError
