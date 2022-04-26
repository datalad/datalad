# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test add_readme"""


from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in,
    assert_repo_status,
    assert_status,
    known_failure_githubci_win,
    ok_startswith,
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
def test_add_readme(path=None):
    ds = Dataset(path).create(force=True)
    ds.save()
    ds.aggregate_metadata()
    assert_repo_status(ds.path)
    assert_status('ok', ds.add_readme())
    # should use default name
    content = open(opj(path, 'README.md')).read()
    ok_startswith(
        content,
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
""".format(
    id=ds.id))
    # make sure that central README references are present
    assert_in(
        """More information on how to install DataLad and [how to install](http://handbook.datalad.org/en/latest/intro/installation.html)
it can be found in the [DataLad Handbook](https://handbook.datalad.org/en/latest/index.html).
""",
        content
    )
    # no unexpectedly long lines
    assert all([len(l) < 160 for l in content.splitlines()])

    # should skip on re-run
    assert_status('notneeded', ds.add_readme())
