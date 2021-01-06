import os.path
from pathlib import Path
import subprocess
import sys
from .utils import (
    assert_in,
    skip_if_on_windows,
    turtle,
    with_tempfile,
)


@turtle
@skip_if_on_windows  # all development for this functionality is moving to datalad-installer
@with_tempfile(mkdir=True)
def test_install_miniconda(tmpdir):
    miniconda_path = os.path.join(tmpdir, "conda")
    subprocess.run(
        [
            sys.executable,
            os.path.join("datalad", "install.py"),
            "miniconda",
            "--batch",
            "--path-miniconda",
            miniconda_path,
        ],
        cwd=Path(__file__).resolve().parent.parent.parent,
        check=True,
    )
    r = subprocess.run(
        [os.path.join(miniconda_path, "bin", "conda"), "create", "-n", "test", "-y"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    )
    assert_in("conda activate test", r.stdout)
