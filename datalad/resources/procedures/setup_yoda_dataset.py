"""Procedure to apply YODA-compatible default setup to a dataset

This procedure assumes a clean dataset that was just created by
`datalad create`.
"""

import sys
import os.path as op

from datalad.distribution.dataset import require_dataset
from datalad.utils import create_tree

# bound dataset methods
import datalad.distribution.add

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='YODA dataset setup')

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
        # all code goes into Git
        '.gitattributes': '** annex.largefiles=nothing',
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

# amend gitattributes
for path in force_in_git:
    abspath = op.join(ds.path, path)
    d = op.dirname(abspath)
    ga_path = op.join(d, '.gitattributes') \
        if op.exists(d) else op.join(ds.path, '.gitattributes')
    with open(ga_path, 'a') as gaf:
        gaf.write('{} annex.largefiles=nothing\n'.format(
            op.relpath(abspath, start=d) if op.exists(d) else path))

# leave clean
# TODO only commit actually changed/added files
ds.add(
    path=[dict(
        path=ds.path,
        type='dataset',
        parentds=ds.path)],
    message="Apply YODA dataset setup",
)
