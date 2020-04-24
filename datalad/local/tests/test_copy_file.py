# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test copy_file command"""


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
    copy_file,
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
    assert_in_results,
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
from datalad.consts import DATALAD_SPECIAL_REMOTE


@with_tempfile(mkdir=True)
@with_tree(tree={
    'webfile1': '123',
    'webfile2': 'abc',
})
@serve_path_via_http
def test_copy_file(workdir, webdir, weburl):
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
    dest_ds.copy_file(src_ds.pathobj / 'myfile1.txt', target_dir=dest_ds.pathobj)
    dest_ds.get('myfile1.txt')
    ok_file_has_content(dest_ds.pathobj / 'myfile1.txt', '123')
    # purposefully pollute the employed tmp folder to check that we do not trip
    # over such a condition
    tmploc = dest_ds.pathobj / '.git' / 'tmp' / 'datalad-copy' / 'some'
    tmploc.parent.mkdir(parents=True)
    tmploc.touch()
    # copy again, but to different target file name
    # (source+dest pair now)
    dest_ds.copy_file(
        [src_ds.pathobj / 'myfile1.txt',
         dest_ds.pathobj / 'renamed.txt'])
    ok_file_has_content(dest_ds.pathobj / 'renamed.txt', '123')
    # copying more than one at once
    dest_ds.copy_file([
        src_ds.pathobj / 'myfile1.txt',
        src_ds.pathobj / 'subdir' / 'myfile2.txt',
        dest_ds.pathobj
    ])
    # copy directly from a non-dataset location
    dest_ds.copy_file(webdir / 'webfile1', target_dir=dest_ds.pathobj)

    # copy from annex dataset into gitrepo
    git_ds = Dataset(workdir / 'git').create(annex=False)
    git_ds.copy_file(src_ds.pathobj / 'subdir' / 'myfile2.txt',
                    target_dir=git_ds.pathobj)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_copy_file_errors(dspath1, dspath2, nondspath):
    ds1 = Dataset(dspath1)
    # no target directory given
    assert_raises(ValueError, ds1.copy_file, 'somefile')
    # using multiple sources and --specs-from
    assert_raises(ValueError, ds1.copy_file, ['1', '2', '3'], specs_from='-')
    # trying to copy to a dir that is not in a dataset
    ds1.create()
    assert_status(
        'error',
        ds1.copy_file('somepath', target_dir=nondspath, on_failure='ignore'))
    # copy into a dataset that is not in the reference dataset
    ds2 = Dataset(dspath2).create()
    assert_status(
        'error',
        ds1.copy_file('somepath', target_dir=dspath2, on_failure='ignore'))

    # attempt to copy from a directory, but no recursion is enabled.
    # use no reference ds to excercise a different code path
    assert_status(
        'impossible', copy_file([nondspath, dspath1], on_failure='ignore'))

    # attempt to copy a file that doesn't exist
    assert_status(
        'impossible', copy_file(['funky', dspath1], on_failure='ignore'))


@with_tempfile(mkdir=True)
@with_tree(tree={
    'webfile1': '123',
})
@serve_path_via_http
def test_copy_file_datalad_specialremote(workdir, webdir, weburl):
    workdir = Path(workdir)
    src_ds = Dataset(workdir / 'src').create()
    # enable datalad special remote
    src_ds.repo.init_remote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external',
         'externaltype={}'.format(DATALAD_SPECIAL_REMOTE),
         'autoenable=true'])
    # put a file into the dataset by URL
    src_ds.download_url('/'.join((weburl, 'webfile1')),
                        path='myfile1.txt')
    # approx test that the file is known to a remote
    # that is not the web remote
    assert_in_results(
        src_ds.repo.whereis('myfile1.txt', output='full').values(),
        here=False,
        description='[{}]'.format(DATALAD_SPECIAL_REMOTE),
    )
    # now a new dataset
    dest_ds = Dataset(workdir / 'dest').create()
    # no special remotes
    eq_(dest_ds.repo.get_special_remotes(), {})
    copy_file([src_ds.pathobj / 'myfile1.txt', dest_ds.pathobj])
    # we have an special remote in the destination dataset now
    assert_in_results(
        dest_ds.repo.get_special_remotes().values(),
        externaltype=DATALAD_SPECIAL_REMOTE,
    )
    # and it works
    dest_ds.drop('myfile1.txt')
    dest_ds.repo.get('myfile1.txt', remote='datalad')
    ok_file_has_content(dest_ds.pathobj / 'myfile1.txt', '123')


@with_tempfile(mkdir=True)
def test_copy_file_into_nonannex(workdir):
    workdir = Path(workdir)
    src_ds = Dataset(workdir / 'src').create()
    (src_ds.pathobj / 'present.txt').write_text('123')
    (src_ds.pathobj / 'gone.txt').write_text('abc')
    src_ds.save()
    src_ds.drop('gone.txt', check=False)

    # destination has no annex
    dest_ds = Dataset(workdir / 'dest').create(annex=False)
    # no issue copying a file that has content
    copy_file([src_ds.pathobj / 'present.txt', dest_ds.pathobj])
    ok_file_has_content(dest_ds.pathobj / 'present.txt', '123')
    # but cannot handle a dropped file, no chance to register
    # availability info in an annex
    assert_status(
        'impossible',
        copy_file([src_ds.pathobj / 'gone.txt', dest_ds.pathobj],
                 on_failure='ignore')
    )


@with_tree(tree={
    'subdir': {
        'file1': '123',
        'file2': 'abc',
    },
})
@with_tempfile(mkdir=True)
def test_copy_file_recursion(srcdir, destdir):
    src_ds = Dataset(srcdir).create(force=True)
    src_ds.save()
    dest_ds = Dataset(destdir).create()
    copy_file([src_ds.pathobj / 'subdir', dest_ds.pathobj], recursive=True)
    # structure is mirrored
    ok_file_has_content(dest_ds.pathobj / 'subdir' / 'file1', '123')
    ok_file_has_content(dest_ds.pathobj / 'subdir' / 'file2', 'abc')
