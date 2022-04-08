#!/usr/bin/env python3
"""Procedure to configure additional metadata types

Additional arguments: <metadata type label> [...]
"""

import sys
import os.path as op

from datalad.consts import (
    DATASET_CONFIG_FILE
)
from datalad.utils import ensure_tuple_or_list
from datalad.distribution.dataset import require_dataset

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

existing_types = ensure_tuple_or_list(
    ds.config.get('datalad.metadata.nativetype', [], get_all=True))

for nt in sys.argv[2:]:
    if nt in existing_types:
        # do not duplicate
        continue
    ds.config.add(
        'datalad.metadata.nativetype',
        nt,
        scope='branch',
        reload=False)

ds.save(
    path=op.join(ds.path, DATASET_CONFIG_FILE),
    message="Configure metadata type(s)",
    result_renderer='disabled'
)
