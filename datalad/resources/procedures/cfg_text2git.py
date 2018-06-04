"""Procedure to configure Git annex to add text files directly to Git"""

import sys
import os.path as op

from datalad.distribution.dataset import require_dataset

# bound dataset methods
import datalad.distribution.add

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

git_attributes_file = op.join(ds.path, '.gitattributes')
with open(git_attributes_file, 'a') as f:
    f.write('* annex.largefiles=(not(mimetype=text/*))\n')

ds.add([dict(
    path=git_attributes_file,
    type='file',
    parentds=ds.path)],
    message="Instruct annex to add text files to Git",
)
