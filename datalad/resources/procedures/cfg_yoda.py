#!/usr/bin/env python3
"""Procedure to apply YODA-compatible default setup to a dataset

This procedure assumes a clean dataset that was just created by
`datalad create`.
"""

import sys
import os.path as op

from datalad.distribution.dataset import require_dataset
from datalad.utils import create_tree

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='YODA dataset setup')

to_modify = [
    ds.pathobj / 'code' / 'README.md',
    ds.pathobj / 'code' / '.gitattributes',
    ds.pathobj / 'README.md',
    ds.pathobj / 'CHANGELOG.md',
    ds.pathobj / '.gitattributes',
]

dirty = [
    s for s in ds.status(
        to_modify,
        result_renderer='disabled',
        return_type='generator',
    )
    if s['state'] != 'clean'
]

if dirty:
    raise RuntimeError(
        'Stopping, because to be modified dataset '
        'content was found dirty: {}'.format(
            [s['path'] for s in dirty]
        ))

README_code = """\
All custom code goes into this directory. All scripts should be written such
that they can be executed from the root of the dataset, and are only using
relative paths for portability.
"""

README_top = """\
# Project <insert name>

## Dataset structure

- All inputs (i.e. building blocks from other sources) are located in
  `inputs/`.
- All custom code is located in `code/`.
"""

tmpl = {
    'code': {
        'README.md': README_code,
    },
    'README.md': README_top,
    'CHANGELOG.md': '',  # TODO
}

# unless taken care of by the template already, each item in here
# will get its own .gitattributes entry to keep it out of the annex
# give relative path to dataset root (use platform notation)
force_in_git = [
    'README.md',
    'CHANGELOG.md',
]

###################################################################
# actually dump everything into the dataset
create_tree(ds.path, tmpl)

# all code goes into Git
ds.repo.set_gitattributes([('*', {'annex.largefiles': 'nothing'})],
                          op.join('code', '.gitattributes'))

# amend gitattributes
ds.repo.set_gitattributes(
    [(p, {'annex.largefiles': 'nothing'}) for p in force_in_git])

# leave clean
ds.save(
    path=to_modify,
    message="Apply YODA dataset setup",
    result_renderer='disabled'
)
