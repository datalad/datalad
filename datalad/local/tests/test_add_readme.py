# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test add_readme"""


from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.tests.utils import (
    assert_repo_status,
    assert_status,
    eq_,
    known_failure_githubci_win,
    with_tree,
)

_ds_template = {
    '.datalad': {
        'config': '''\
[datalad "metadata"]
        nativetype = frictionless_datapackage
'''},
    'datapackage.json': '''\
{
    "title": "demo_ds",
    "description": "this is for play",
    "license": "PDDL",
    "author": [
        "Betty",
        "Tom"
    ]
}
'''}


@known_failure_githubci_win  # fails since upgrade to 8.20200226-g2d3ef2c07
@with_tree(_ds_template)
def test_add_readme(path):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.aggregate_metadata()
    assert_repo_status(ds.path)
    assert_status('ok', ds.add_readme())
    # should use default name
    eq_(
        open(opj(path, 'README.md')).read(),
        """\
# Dataset "demo_ds"

this is for play

### Authors

- Betty
- Tom

### License

PDDL

## General information

This is a DataLad dataset (id: {id}).

For more information on DataLad and on how to work with its datasets,
see the DataLad documentation at: http://handbook.datalad.org
""".format(
    id=ds.id))

    # should skip on re-run
    assert_status('notneeded', ds.add_readme())
