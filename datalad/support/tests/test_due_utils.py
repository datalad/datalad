from ...distribution import dataset as dataset_mod
from ...distribution.dataset import Dataset
from .. import due_utils
from ..due_utils import duecredit_dataset

from ..due import due

from ...tests.utils import (
    assert_raises,
    eq_,
    integration,
    ok_,
    SkipTest,
    skip_if_no_module,
    swallow_logs,
    with_tempfile,
)
import logging
from mock import patch


@with_tempfile(mkdir=True)
@patch.object(due_utils, 'Doi')
@patch.object(due_utils, 'Text')
def test_duecredit_dataset(path, Text, Doi):
    dataset = Dataset(path)

    # Verify that we do not call duecredit_dataset if due is not enabled
    # Seems cant patch.object.enabled so we will just test differently
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
        with swallow_logs(new_level=logging.WARNING) as cml:
            duecredit_dataset(dataset)  # should not crash or anything
            # since no metadata - we issue warning and return without citing
            # anything
            cml.assert_logged(
                regex='.*Failed to obtain metadata.*Will not provide duecredit.*'
            )
        mcite.assert_not_called()

    # Let's provide some, but no relevant, metadata
    with patch.object(due, 'cite') as mcite, \
        patch.object(dataset, 'metadata') as mmetadata:
        mmetadata.return_value = {'metadata': {'mumbo': {'jumbo': True}}}
        duecredit_dataset(dataset)
        # We resort to catch all
        mcite.assert_called_once_with(
            # TODO: make a proper class for Text/Doi not just magical mock
            Text("CONTENT ISN'T CHECKED"), # ""DataLad dataset at %s" % dataset.path),
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
        # TODO: somehow if worked for Text() - doesn't work for Doi
        #       Claims that we didn't specify doi for Doi() in expected
        # mcite.assert_called_once_with(
        #     # TODO: make a proper class for Text/Doi not just magical mock
        #     Doi(doi), # ""DataLad dataset at %s" % dataset.path),
        #     description='ds name',
        #     path='datalad:%s' % dataset.id[:8],
        #     version=None
        # )

