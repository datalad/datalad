import logging
from unittest.mock import patch

from ...distribution import dataset as dataset_mod
from ...distribution.dataset import Dataset
from ...tests.utils_pytest import (
    swallow_logs,
    with_tempfile,
)
from ..due import (
    Doi,
    Text,
    due,
)
from ..due_utils import duecredit_dataset
from ..external_versions import external_versions


@with_tempfile(mkdir=True)
def test_duecredit_dataset(path=None):
    dataset = Dataset(path)

    # Verify that we do not call duecredit_dataset if due is not enabled
    # Seems can't patch.object.enabled so we will just test differently
    # depending on either enabled or not
    if not due.active:
        with patch.object(dataset_mod, 'duecredit_dataset') as cmdc:
            dataset.create()
            cmdc.assert_not_called()
    else:
        with patch.object(dataset_mod, 'duecredit_dataset') as cmdc:
            dataset.create()
            cmdc.assert_called_once_with(dataset)


    # note: doesn't crash even if we call it incorrectly (needs dataset)
    duecredit_dataset()

    # No metadata -- no citation ATM.
    # TODO: possibly reconsider - may be our catch-all should be used there
    # as well
    with patch.object(due, 'cite') as mcite:
        with swallow_logs(new_level=logging.DEBUG) as cml:
            duecredit_dataset(dataset)  # should not crash or anything
            # since no metadata - we issue warning and return without citing
            # anything
            cml.assert_logged(
                regex='.*Failed to obtain metadata.*Will not provide duecredit.*'
            )
        mcite.assert_not_called()

    # Below we will rely on duecredit Entries being comparable, so if
    # duecredit is available and does not provide __cmp__ we make it for now
    # Whenever https://github.com/duecredit/duecredit/pull/148 is merged, and
    # probably 0.7.1 released - we will eventually remove this monkey patching.
    # Checking if __eq__ was actually provided seems tricky on py2, so decided
    # to just do version comparison
    try:
        if external_versions['duecredit'] < '0.7.1':
            from duecredit.entries import DueCreditEntry
            def _entry_eq(self, other):
                return (
                        (self._rawentry == other._rawentry) and
                        (self._key == other._key)
                )
            DueCreditEntry.__eq__ = _entry_eq
    except:
        # assume that not present so donothing stubs would be used, and
        # we will just compare Nones
        pass

    # Let's provide some, but no relevant, metadata
    with patch.object(due, 'cite') as mcite, \
        patch.object(dataset, 'metadata') as mmetadata:
        mmetadata.return_value = {'metadata': {'mumbo': {'jumbo': True}}}
        duecredit_dataset(dataset)
        # We resort to catch all
        mcite.assert_called_once_with(
            # TODO: make a proper class for Text/Doi not just magical mock
            Text("DataLad dataset at %s" % dataset.path),
            description='DataLad dataset %s' % dataset.id,
            path='datalad:%s' % dataset.id[:8],
            version=None
        )

    # A sample call with BIDS dataset metadata
    with patch.object(due, 'cite') as mcite, \
        patch.object(dataset, 'metadata') as mmetadata:
        doi = 'xxx.12/12.345'
        mmetadata.return_value = {
            'metadata': {
                'bids': {
                    # here we would test also to be case insensitive
                    'DatasetDoi': doi,
                    'name': "ds name",
            }}}
        duecredit_dataset(dataset)
        mcite.assert_called_once_with(
            Doi(doi), # ""DataLad dataset at %s" % dataset.path),
            description='ds name',
            path='datalad:%s' % dataset.id[:8],
            version=None
        )

