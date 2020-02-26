from datalad.api import (
    clone,
)
from datalad.utils import (
    Path,
)
from datalad.tests.utils import (
    skip_if_on_windows,
    skip_ssh,
    with_tempfile,
)

from datalad.customremotes.tests.ria_utils import (
    skip_non_ssh,
)


@skip_non_ssh
@skip_if_on_windows
@with_tempfile
@with_tempfile
def test_binary_data_local(dspath, store):
    # make sure, special remote deals with binary data and doesn't
    # accidentally involve any decode/encode etc.

    url = "https://github.com/psychoinformatics-de/studyforrest-data-phase2"
    file = Path("sub-01/ses-movie/func/sub-01_ses-movie_task-movie_run-1_bold"
                ".nii.gz")

    ds = clone(url, dspath)
    ds.get(file)

    ds.create_sibling_ria("ria+{}".format(Path(store).as_uri()),
                          "datastore")

    ds.publish(to="datastore", transfer_data="all")
    ds.drop(file)
    ds.get(file, source="datastore-ria")


@skip_ssh
@skip_if_on_windows
@with_tempfile
@with_tempfile
def test_binary_data_ssh(dspath, store):
    # make sure, special remote deals with binary data and doesn't
    # accidentally involve any decode/encode etc.

    url = "https://github.com/psychoinformatics-de/studyforrest-data-phase2"
    file = Path("sub-01/ses-movie/func/sub-01_ses-movie_task-movie_run-1_bold"
                ".nii.gz")

    ds = clone(url, dspath)
    ds.get(str(file))

    ds.create_sibling_ria("ria+ssh://localhost{}"
                          "".format(Path(store).as_posix()),
                          "datastore")

    ds.publish(to="datastore", transfer_data="all")
    ds.drop(str(file))
    ds.get(file, source="datastore-ria")
