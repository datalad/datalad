# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test copy_file command"""


from os.path import join as opj

from datalad.api import copy_file
from datalad.consts import DATALAD_SPECIAL_REMOTE
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in_results,
    assert_raises,
    assert_repo_status,
    assert_status,
    chpwd,
    eq_,
    nok_,
    ok_,
    ok_file_has_content,
    serve_path_via_http,
    slow,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path


@with_tempfile(mkdir=True)
@with_tree(tree={
    'webfile1': '123',
    'webfile2': 'abc',
})
@serve_path_via_http
def test_copy_file(workdir=None, webdir=None, weburl=None):
    workdir = Path(workdir)
    webdir = Path(webdir)
    src_ds = Dataset(workdir / 'src').create()
    # put a file into the dataset by URL and drop it again
    src_ds.download_url('/'.join((weburl, 'webfile1')),
                        path='myfile1.txt')
    src_ds.download_url('/'.join((weburl, 'webfile2')),
                        path=opj('subdir', 'myfile2.txt'))
    ok_file_has_content(src_ds.pathobj / 'myfile1.txt', '123')
    # now create a fresh dataset
    dest_ds = Dataset(workdir / 'dest').create()
    if dest_ds.repo._check_version_kludges("fromkey-supports-unlocked") or \
       not dest_ds.repo.is_managed_branch():
        # unless we have a target ds on a cripples FS (where `annex fromkey`
        # doesn't work until after 8.20210428), we can even drop the file
        # content in the source repo
        src_ds.drop('myfile1.txt', reckless='kill')
        nok_(src_ds.repo.file_has_content('myfile1.txt'))
    # copy the file from the source dataset into it.
    # it must copy enough info to actually put datalad into the position
    # to obtain the file content from the original URL
    dest_ds.copy_file(src_ds.pathobj / 'myfile1.txt')
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
    dest_ds.copy_file(webdir / 'webfile1')

    # copy from annex dataset into gitrepo
    git_ds = Dataset(workdir / 'git').create(annex=False)
    git_ds.copy_file(src_ds.pathobj / 'subdir' / 'myfile2.txt')


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_copy_file_errors(dspath1=None, dspath2=None, nondspath=None):
    ds1 = Dataset(dspath1)
    # nothing given
    assert_raises(ValueError, copy_file)
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
    # use no reference ds to exercise a different code path
    assert_status(
        'impossible', copy_file([nondspath, dspath1], on_failure='ignore'))

    # attempt to copy a file that doesn't exist
    assert_status(
        'impossible', copy_file(['funky', dspath1], on_failure='ignore'))

    # attempt to copy a file without a destination given
    assert_raises(ValueError, copy_file, 'somepath')
    assert_status(
        'impossible', copy_file(specs_from=['somepath'], on_failure='ignore'))


@slow  # 11sec + ? on travis
@with_tempfile(mkdir=True)
@with_tree(tree={
    'webfile1': '123',
    'webfile2': 'abc',
})
@serve_path_via_http
def test_copy_file_datalad_specialremote(workdir=None, webdir=None, weburl=None):
    workdir = Path(workdir)
    src_ds = Dataset(workdir / 'src').create()
    # enable datalad special remote
    src_ds.repo.init_remote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external',
         'externaltype={}'.format(DATALAD_SPECIAL_REMOTE),
         'autoenable=true'])
    # put files into the dataset by URL
    src_ds.download_url('/'.join((weburl, 'webfile1')),
                        path='myfile1.txt')
    src_ds.download_url('/'.join((weburl, 'webfile2')),
                        path='myfile2.txt')
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
    # must call with a dataset to get change saved, in order for drop
    # below to work properly without getting in reckless mode
    dest_ds.copy_file([src_ds.pathobj / 'myfile1.txt', dest_ds.pathobj])
    # we have an special remote in the destination dataset now
    assert_in_results(
        dest_ds.repo.get_special_remotes().values(),
        externaltype=DATALAD_SPECIAL_REMOTE,
    )
    # and it works
    dest_ds.drop('myfile1.txt')
    dest_ds.repo.get('myfile1.txt', remote='datalad')
    ok_file_has_content(dest_ds.pathobj / 'myfile1.txt', '123')

    # now replace file in dest with a different content at the same path
    # must call with a dataset to get change saved, in order for drop
    dest_ds.copy_file([src_ds.pathobj / 'myfile2.txt',
                       dest_ds.pathobj / 'myfile1.txt'])
    dest_ds.drop('myfile1.txt')
    dest_ds.repo.get('myfile1.txt', remote='datalad')
    # no gets the "same path" but yields different content
    ok_file_has_content(dest_ds.pathobj / 'myfile1.txt', 'abc')


@with_tempfile(mkdir=True)
def test_copy_file_into_nonannex(workdir=None):
    workdir = Path(workdir)
    src_ds = Dataset(workdir / 'src').create()
    (src_ds.pathobj / 'present.txt').write_text('123')
    (src_ds.pathobj / 'gone.txt').write_text('abc')
    src_ds.save()
    src_ds.drop('gone.txt', reckless='kill')

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
def test_copy_file_recursion(srcdir=None, destdir=None):
    src_ds = Dataset(srcdir).create(force=True)
    src_ds.save()
    dest_ds = Dataset(destdir).create()
    copy_file([src_ds.pathobj / 'subdir', dest_ds.pathobj], recursive=True)
    # structure is mirrored
    ok_file_has_content(dest_ds.pathobj / 'subdir' / 'file1', '123')
    ok_file_has_content(dest_ds.pathobj / 'subdir' / 'file2', 'abc')


@with_tree(tree={
    'lvl1': {
        'file1': '123',
        'lvl2' : {
            'file2': 'abc',
        },
    },
})
@with_tempfile(mkdir=True)
def test_copy_file_into_dshierarchy(srcdir=None, destdir=None):
    srcdir = Path(srcdir)
    src_ds = Dataset(srcdir).create(force=True)
    src_ds.save()
    # now build two nested datasets, such that lvl2 ends up in a subdataset
    dest_ds = Dataset(destdir).create()
    dest_ds.create(dest_ds.pathobj / 'lvl2')
    assert_repo_status(dest_ds.path)

    dest_ds.copy_file([src_ds.pathobj / 'lvl1', dest_ds.pathobj], recursive=True)
    assert_repo_status(dest_ds.path)

    # we get the same structure as the input, just distributed across
    # nested datasets
    eq_(*[
        sorted(
            r for r in d.status(result_xfm='relpaths', result_renderer='disabled')
            # filter out subdataset entry in dest_ds
            if r not in ('lvl2', '.gitmodules'))
        for d in (src_ds, dest_ds)
    ])


@slow  # 11sec on Yarik's laptop
@with_tree(tree={
    'lvl1': {
        'file1': '123',
        'lvl2' : {
            'file2': 'abc',
        },
    },
})
@with_tempfile(mkdir=True)
def test_copy_file_specs_from(srcdir=None, destdir=None):
    srcdir = Path(srcdir)
    destdir = Path(destdir)
    files = [p for p in srcdir.glob('**/*') if not p.is_dir()]
    # plain list of absolute path objects
    r_srcabs, res = _check_copy_file_specs_from(
        srcdir, destdir / 'srcabs',
        files)
    # same, but with relative paths
    with chpwd(srcdir):
        r_srcrel, res = _check_copy_file_specs_from(
            srcdir, destdir / 'srcrel',
            [p.relative_to(srcdir) for p in files])
    # same, but as strings
    r_srcabs_str, res = _check_copy_file_specs_from(
        srcdir, destdir / 'srcabs_str',
        [str(p) for p in files])
    with chpwd(srcdir):
        r_srcrel_str, res = _check_copy_file_specs_from(
            srcdir, destdir / 'srcrel_str',
            [str(p.relative_to(srcdir)) for p in files])
    # same, but with src/dest pairs
    r_srcdestabs_str, res = _check_copy_file_specs_from(
        srcdir, destdir / 'srcdestabs_str',
        ['{}\0{}'.format(
            str(p),
            str(destdir / 'srcdestabs_str' / p.name))
         for p in files])

    # all methods lead to the same dataset structure
    for a, b in ((r_srcabs, r_srcrel),
                 (r_srcabs, r_srcabs_str),
                 (r_srcabs, r_srcrel_str),
                 (r_srcabs, r_srcdestabs_str)):
        eq_(*[
            sorted(
                r for r in d.status(result_xfm='relpaths', result_renderer='disabled'))
            for d in (a, b)
        ])

    # fail on destination outside of the dest repo
    res = copy_file(specs_from=[
        '{}\0{}'.format(
            str(p),
            str(destdir / 'srcdest_wrong' / p.relative_to(srcdir)))
        for p in files],
        on_failure='ignore')
    assert_status('error', res)


def _check_copy_file_specs_from(srcdir, destdir, specs, **kwargs):
    ds = Dataset(destdir).create()
    res = ds.copy_file(specs_from=specs, **kwargs)
    return ds, res


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_copy_file_prevent_dotgit_placement(srcpath=None, destpath=None):
    src = Dataset(srcpath).create()
    sub = src.create('sub')
    dest = Dataset(destpath).create()

    # recursion doesn't capture .git/
    dest.copy_file(sub.path, recursive=True)
    nok_((dest.pathobj / 'sub' / '.git').exists())

    # explicit instruction results in failure
    assert_status(
        'impossible',
        dest.copy_file(sub.pathobj / '.git', recursive=True,
                       on_failure='ignore'))

    # same when the source has an OK name, but the dest now
    assert_in_results(
        dest.copy_file(
            [sub.pathobj / '.git' / 'config',
             dest.pathobj / 'some' / '.git'], on_failure='ignore'),
        status='impossible',
        action='copy_file')

    # The last path above wasn't treated as a target directory because it
    # wasn't an existing directory. We also guard against a '.git' in the
    # target directory code path, though the handling is different.
    with assert_raises(ValueError):
        dest.copy_file([sub.pathobj / '.git' / 'config',
                        dest.pathobj / '.git'])

    # A source path can have a leading .git/ if the destination is outside of
    # .git/.
    nok_((dest.pathobj / "config").exists())
    dest.copy_file(sub.pathobj / '.git' / 'config')
    ok_((dest.pathobj / "config").exists())

    target = dest.pathobj / 'some'
    nok_(target.exists())
    dest.copy_file([sub.pathobj / '.git' / 'config', target])
    ok_(target.exists())

    # But we only waste so many cycles trying to prevent foot shooting. This
    # next one sneaks by because only .name, not all upstream parts, is checked
    # for each destination that comes out of _yield_specs().
    badobj = dest.pathobj / '.git' / 'objects' / 'i-do-not-exist'
    dest.copy_file([sub.pathobj / '.git' / 'config', badobj])
    ok_(badobj.exists())


@with_tempfile
@with_tempfile
@with_tempfile
def test_copy_file_nourl(serv_path=None, orig_path=None, tst_path=None):
    """Tests availability transfer to normal git-annex remote"""
    # prep source dataset that will have the file content
    srv_ds = Dataset(serv_path).create()
    (srv_ds.pathobj / 'myfile.dat').write_text('I am content')
    (srv_ds.pathobj / 'noavail.dat').write_text('null')
    srv_ds.save()
    srv_ds.drop('noavail.dat', reckless='kill')
    # make an empty superdataset, with the test dataset as a subdataset
    orig_ds = Dataset(orig_path).create()
    orig_ds.clone(source=serv_path, path='serv')
    assert_repo_status(orig_ds.path)
    # now copy the test file into the superdataset
    no_avail_file = orig_ds.pathobj / 'serv' / 'noavail.dat'
    assert_in_results(
        orig_ds.copy_file(no_avail_file, on_failure='ignore'),
        status='impossible',
        message='no known location of file content',
        path=str(no_avail_file),
    )
