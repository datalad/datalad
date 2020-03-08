# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

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

from datalad.distributed.tests.ria_utils import (
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
    file = Path("code/stimulus/visualarea_localizer/img/body01.png")

    ds = clone(url, dspath)
    ds.get(file)

    ds.create_sibling_ria("ria+{}".format(Path(store).as_uri()),
                          "datastore")

    ds.publish(to="datastore", transfer_data="all")
    ds.drop(file)
    ds.get(file, source="datastore-storage")


@skip_ssh
@skip_if_on_windows
@with_tempfile
@with_tempfile
def test_binary_data_ssh(dspath, store):
    # make sure, special remote deals with binary data and doesn't
    # accidentally involve any decode/encode etc.

    url = "https://github.com/psychoinformatics-de/studyforrest-data-phase2"
    file = Path("code/stimulus/visualarea_localizer/img/body01.png")

    ds = clone(url, dspath)
    ds.get(str(file))

    ds.create_sibling_ria("ria+ssh://localhost{}"
                          "".format(Path(store).as_posix()),
                          "datastore")

    ds.publish(to="datastore", transfer_data="all")
    ds.drop(str(file))
    ds.get(file, source="datastore-storage")
