"""Procedure to configure additional metadata types

Additional arguments: <metadata type label> [...]
"""

import sys
import os.path as op

from datalad.consts import (
    DATASET_CONFIG_FILE
)
from datalad.distribution.dataset import require_dataset

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

for nt in sys.argv[2:]:
    if nt in ds.config.get('datalad.metadata.nativetype', []):
        # do not duplicate
        continue
    ds.config.add(
        'datalad.metadata.nativetype',
        nt,
        where='dataset',
        reload=False)

ds.save(
    path=[dict(
        path=op.join(ds.path, DATASET_CONFIG_FILE),
        type='file',
        parentds=ds.path)],
    message="Configure metadata type(s)",
)
