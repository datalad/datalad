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

## DataLad datasets and how to use them

This repository is a [DataLad](https://www.datalad.org/) dataset. It provides
fine-grained data access down to the level of individual files, and allows for
tracking future updates. In order to use this repository for data retrieval,
[DataLad](https://www.datalad.org/) is required. It is a free and open source
command line tool, available for all major operating systems, and builds up on
Git and [git-annex](https://git-annex.branchable.com/) to allow sharing,
synchronizing, and version controlling collections of large files.

More information on how to install DataLad and [how to install](http://handbook.datalad.org/en/latest/intro/installation.html)
it can be found in the [DataLad Handbook](https://handbook.datalad.org/en/latest/index.html).

### Get the dataset

A DataLad dataset can be `cloned` by running

```
datalad clone <url>
```

Once a dataset is cloned, it is a light-weight directory on your local machine.
At this point, it contains only small metadata and information on the identity
of the files in the dataset, but not actual *content* of the (sometimes large)
data files.

### Retrieve dataset content

After cloning a dataset, you can retrieve file contents by running

```
datalad get <path/to/directory/or/file>
```

This command will trigger a download of the files, directories, or subdatasets
you have specified.

DataLad datasets can contain other datasets, so called *subdatasets*.  If you
clone the top-level dataset, subdatasets do not yet contain metadata and
information on the identity of files, but appear to be empty directories. In
order to retrieve file availability metadata in subdatasets, run

```
datalad get -n <path/to/subdataset>
```

Afterwards, you can browse the retrieved metadata to find out about subdataset
contents, and retrieve individual files with `datalad get`.  If you use
`datalad get <path/to/subdataset>`, all contents of the subdataset will be
downloaded at once.

### Stay up-to-date

DataLad datasets can be updated. The command `datalad update` will *fetch*
updates and store them on a different branch (by default
`remotes/origin/master`). Running

```
datalad update --merge
```

will *pull* available updates and integrate them in one go.

### Find out what has been done

DataLad datasets contain their history in the ``git log``.  By running ``git
log`` (or a tool that displays Git history) in the dataset or on specific
files, you can find out what has been done to the dataset or to individual
files by whom, and when.
""".format(
    id=ds.id))

    # should skip on re-run
    assert_status('notneeded', ds.add_readme())
