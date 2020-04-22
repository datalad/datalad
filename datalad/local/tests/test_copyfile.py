# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test copyfile command"""


import os
from os.path import (
    join as opj,
    relpath,
    pardir,
)

from datalad.distribution.dataset import Dataset
from datalad.api import (
    clone,
    create,
    copyfile,
)
from datalad.utils import (
    chpwd,
    on_windows,
    Path,
    PurePosixPath,
)
from datalad.tests.utils import (
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    nok_,
    ok_file_has_content,
    serve_path_via_http,
    with_tempfile,
    with_tree,
)


@with_tempfile(mkdir=True)
@with_tree(tree={
    'webfile1': '123',
    'webfile2': 'abc',
})
@serve_path_via_http
def test_copyfile(workdir, webdir, weburl):
    workdir = Path(workdir)
    webdir = Path(webdir)
    src_ds = Dataset(workdir / 'src').create()
    # put a file into the dataset by URL and drop it again
    src_ds.download_url('/'.join((weburl, 'webfile1')),
                        path='myfile1.txt')
    src_ds.download_url('/'.join((weburl, 'webfile2')),
                        path=opj('subdir', 'myfile2.txt'))
    ok_file_has_content(src_ds.pathobj / 'myfile1.txt', '123')
    src_ds.drop('myfile1.txt', check=False)
    nok_(src_ds.repo.file_has_content('myfile1.txt'))
    # now create a fresh dataset
    dest_ds = Dataset(workdir / 'dest').create()
    # copy the file from the source dataset into it.
    # it must copy enough info to actually put datalad into the position
    # to obtain the file content from the original URL
    dest_ds.copyfile(src_ds.pathobj / 'myfile1.txt', target_dir=dest_ds.pathobj)
    dest_ds.get('myfile1.txt')
    ok_file_has_content(dest_ds.pathobj / 'myfile1.txt', '123')
    # doing it again works fine, using different call style
    # (source+dest pair)
    # purposefully pollute the employed tmp folder to check that we do not trip
    # over such a condition
    tmploc = dest_ds.pathobj / '.git' / 'tmp' / 'datalad-copy' / 'some'
    tmploc.parent.mkdir(parents=True)
    tmploc.touch()
    dest_ds.copyfile([src_ds.pathobj / 'myfile1.txt', dest_ds.pathobj])
    # copying more than one at once
    dest_ds.copyfile([
        src_ds.pathobj / 'myfile1.txt',
        src_ds.pathobj / 'subdir' / 'myfile2.txt',
        dest_ds.pathobj
    ])
    # copy directly from a non-dataset location
    dest_ds.copyfile(webdir / 'webfile1', target_dir=dest_ds.pathobj)

    # copy from annex dataset into gitrepo
    git_ds = Dataset(workdir / 'git').create(annex=False)
    git_ds.copyfile(src_ds.pathobj / 'subdir' / 'myfile2.txt',
                    target_dir=git_ds.pathobj)




@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_copyfile_errors(dspath1, dspath2, nondspath):
    ds1 = Dataset(dspath1)
    # no target directory given
    assert_raises(ValueError, ds1.copyfile, 'somefile')
    # using multiple sources and --specs-from
    assert_raises(ValueError, ds1.copyfile, ['1', '2', '3'], specs_from='-')
    # trying to copy to a dir that is not in a dataset
    assert_status(
        'error',
        ds1.copyfile('somepath', target_dir=nondspath, on_failure='ignore'))
    # copy into a dataset that is not in the reference dataset
    ds1.create()
    ds2 = Dataset(dspath2).create()
    assert_status(
        'error',
        ds1.copyfile('somepath', target_dir=dspath2, on_failure='ignore'))

    # attempt to copy from a directory, but no recursion is enabled.
    # use no reference ds to excercise a different code path
    assert_status(
        'impossible', copyfile([nondspath, dspath1], on_failure='ignore'))
