"""Procedure to configure Git annex to add text files directly to Git"""

import sys
import os.path as op

from datalad.distribution.dataset import require_dataset

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

annex_largefiles = '(not(mimetype=text/*))'
attrs = ds.repo.get_gitattributes('*')
if not attrs.get('*', {}).get(
        'annex.largefiles', None) == annex_largefiles:
    ds.repo.set_gitattributes([
        ('*', {'annex.largefiles': annex_largefiles})])

git_attributes_file = op.join(ds.path, '.gitattributes')
ds.add([dict(
    path=git_attributes_file,
    type='file',
    parentds=ds.path)],
    message="Instruct annex to add text files to Git",
)
