
from datalad.distribution.dataset import Dataset
from datalad.tests.utils import with_tempfile


@with_tempfile(mkdir=True)
def test_metadata_without_gen4(ds_path=None):
    ds = Dataset(ds_path).create(force=True, annex=False)
    ds.save(result_renderer="disabled")
    ds.configuration(
        action="set",
        spec="datalad.metadata.nativetype=datalad_core",
        result_renderer="disabled"
    )
    ds.aggregate_metadata(result_renderer="disabled")
    for result in tuple(ds.metadata(result_renderer="disabled")):
        assert result['status'] == 'ok'
