# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test subdataset command"""


import os
from os.path import join as opj
from os.path import (
    pardir,
    relpath,
)

from datalad.api import (
    clone,
    create,
    subdatasets,
)
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_false,
    assert_in,
    assert_not_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    assert_true,
    eq_,
    slow,
    with_tempfile,
)
from datalad.utils import (
    Path,
    PurePosixPath,
    chpwd,
)


def _p(rpath):
    return str(Path(PurePosixPath(rpath)))


@slow  # 13sec on travis
@with_tempfile
@with_tempfile
def test_get_subdatasets(origpath=None, path=None):
    # setup
    orig = Dataset(origpath).create()
    orig_sub = orig.create('sub dataset1')
    # 2nd-level
    for s in ('2', 'sub sub dataset1', 'subm 1'):
        orig_sub.create(s)
    # 3rd-level
    for s in ('2', 'subm 1'):
        orig_sub.create(Path('sub sub dataset1', s))
    orig.save(recursive=True)
    assert_repo_status(orig.path)

    # tests
    ds = clone(source=origpath, path=path)
    # one more subdataset with a name that could ruin config option parsing
    # no trailing dots on windows and its crippled FS mounted on linux!
    dots = str(Path('subdir') / ('.lots.of.dots'))
    ds.create(dots)
    # mitigate https://github.com/datalad/datalad/issues/4267
    ds.save()
    eq_(ds.subdatasets(recursive=True, state='absent', result_xfm='relpaths'), [
        'sub dataset1'
    ])
    ds.get('sub dataset1')
    eq_(ds.subdatasets(recursive=True, state='absent', result_xfm='relpaths'), [
        _p('sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1'),
        _p('sub dataset1/subm 1'),
    ])
    # obtain key subdataset, so all leaf subdatasets are discoverable
    ds.get(opj('sub dataset1', 'sub sub dataset1'))
    eq_(ds.subdatasets(result_xfm='relpaths'), ['sub dataset1', dots])
    eq_([(r['parentds'], r['path']) for r in ds.subdatasets()],
        [(path, opj(path, 'sub dataset1')),
         (path, opj(path, dots))])
    all_subs = [
        _p('sub dataset1'),
        _p('sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1'),
        _p('sub dataset1/sub sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1/subm 1'),
        _p('sub dataset1/subm 1'),
        dots,
    ]
    eq_(ds.subdatasets(recursive=True, result_xfm='relpaths'), all_subs)
    with chpwd(str(ds.pathobj)):
        # imitate cmdline invocation w/ no dataset argument
        eq_(subdatasets(dataset=None,
                        path=[],
                        recursive=True,
                        result_xfm='relpaths'),
            all_subs)

    # redo, but limit to specific paths
    eq_(
        ds.subdatasets(
            path=[_p('sub dataset1/2'), _p('sub dataset1/sub sub dataset1')],
            recursive=True, result_xfm='relpaths'),
        [
            _p('sub dataset1/2'),
            _p('sub dataset1/sub sub dataset1'),
            _p('sub dataset1/sub sub dataset1/2'),
            _p('sub dataset1/sub sub dataset1/subm 1'),
        ]
    )
    eq_(
        ds.subdatasets(
            path=['sub dataset1'],
            recursive=True, result_xfm='relpaths'),
        [
            _p('sub dataset1'),
            _p('sub dataset1/2'),
            _p('sub dataset1/sub sub dataset1'),
            _p('sub dataset1/sub sub dataset1/2'),
            _p('sub dataset1/sub sub dataset1/subm 1'),
            _p('sub dataset1/subm 1'),
        ]
    )
    with chpwd(str(ds.pathobj / 'subdir')):
        # imitate cmdline invocation w/ no dataset argument
        # -> curdir limits the query, when no info is given
        eq_(subdatasets(dataset=None,
                        path=[],
                        recursive=True,
                        result_xfm='paths'),
            [str(ds.pathobj / dots)]
        )
        # but with a dataset explicitly given, even if just as a path,
        # curdir does no limit the query
        eq_(subdatasets(dataset=os.pardir,
                        path=None,
                        recursive=True,
                        result_xfm='relpaths'),
            [_p('sub dataset1'),
             _p('sub dataset1/2'),
             _p('sub dataset1/sub sub dataset1'),
             _p('sub dataset1/sub sub dataset1/2'),
             _p('sub dataset1/sub sub dataset1/subm 1'),
             _p('sub dataset1/subm 1'),
             dots]
        )
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, bottomup=True, result_xfm='relpaths'), [
        _p('sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1/subm 1'),
        _p('sub dataset1/sub sub dataset1'),
        _p('sub dataset1/subm 1'),
        _p('sub dataset1'),
        dots,
    ])
    eq_(ds.subdatasets(recursive=True, state='present', result_xfm='relpaths'), [
        _p('sub dataset1'),
        _p('sub dataset1/sub sub dataset1'),
        dots,
    ])
    eq_([(relpath(r['parentds'], start=ds.path), relpath(r['path'], start=ds.path))
         for r in ds.subdatasets(recursive=True)], [
        (os.curdir, 'sub dataset1'),
        ('sub dataset1', _p('sub dataset1/2')),
        ('sub dataset1', _p('sub dataset1/sub sub dataset1')),
        (_p('sub dataset1/sub sub dataset1'), _p('sub dataset1/sub sub dataset1/2')),
        (_p('sub dataset1/sub sub dataset1'), _p('sub dataset1/sub sub dataset1/subm 1')),
        ('sub dataset1', _p('sub dataset1/subm 1')),
        (os.curdir, dots),
    ])
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, recursion_limit=0),
        [])
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, recursion_limit=1, result_xfm='relpaths'),
        ['sub dataset1', _p(dots)])
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, recursion_limit=2, result_xfm='relpaths'),
        [
        'sub dataset1',
        _p('sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1'),
        _p('sub dataset1/subm 1'),
        dots,
    ])
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        #for prop in ('gitmodule_url', 'state', 'gitshasum', 'gitmodule_name'):
        for prop in ('gitmodule_url', 'gitshasum', 'gitmodule_name'):
            assert_in(prop, r)
        # random property is unknown
        assert_not_in('mike', r)

    # now add info to all datasets
    res = ds.subdatasets(
        recursive=True,
        set_property=[('mike', 'slow'),
                      ('expansion', '<{refds_relname}>')])
    assert_status('ok', res)
    for r in res:
        if r.get('action') != 'subdataset':
            continue
        eq_(r['gitmodule_mike'], 'slow')
        eq_(r['gitmodule_expansion'], relpath(r['path'], r['refds']).replace(os.sep, '-'))
    # plain query again to see if it got into the files
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        eq_(r['gitmodule_mike'], 'slow')
        eq_(r['gitmodule_expansion'], relpath(r['path'], r['refds']).replace(os.sep, '-'))

    # and remove again
    res = ds.subdatasets(recursive=True, delete_property='mike')
    assert_status('ok', res)
    for r in res:
        for prop in ('gitmodule_mike'):
            assert_not_in(prop, r)
    # and again, because above yields on the fly edit
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        for prop in ('gitmodule_mike'):
            assert_not_in(prop, r)

    #
    # test --contains
    #
    target_sub = _p('sub dataset1/sub sub dataset1/subm 1')
    # give the closest direct subdataset
    eq_(ds.subdatasets(contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1'])
    # should find the actual subdataset trail
    eq_(ds.subdatasets(recursive=True,
                       contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1',
         _p('sub dataset1/sub sub dataset1'),
         _p('sub dataset1/sub sub dataset1/subm 1')])
    # doesn't affect recursion limit
    eq_(ds.subdatasets(recursive=True, recursion_limit=2,
                       contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1',
         _p('sub dataset1/sub sub dataset1')])
    # for a direct dataset path match, return the matching dataset
    eq_(ds.subdatasets(recursive=True,
                       contains=target_sub,
                       result_xfm='relpaths'),
        ['sub dataset1',
         _p('sub dataset1/sub sub dataset1'),
         _p('sub dataset1/sub sub dataset1/subm 1')])
    # but it has to be a subdataset, otherwise no match
    # which is what get_containing_subdataset() used to do
    assert_status('impossible',
                  ds.subdatasets(contains=ds.path, on_failure='ignore'))

    # 'impossible' if contains is bullshit
    assert_status('impossible',
                  ds.subdatasets(recursive=True,
                                 contains='impossible_yes',
                                 on_failure='ignore'))

    assert_status('impossible',
                  ds.subdatasets(recursive=True,
                                 contains=opj(pardir, 'impossible_yes'),
                                 on_failure='ignore'))

    eq_(ds.subdatasets(
        recursive=True,
        contains=[target_sub, _p('sub dataset1/2')],
        result_xfm='relpaths'), [
        'sub dataset1',
        _p('sub dataset1/2'),
        _p('sub dataset1/sub sub dataset1'),
        _p('sub dataset1/sub sub dataset1/subm 1'),
    ])


@with_tempfile
def test_state(path=None):
    ds = Dataset.create(path)
    sub = ds.create('sub')
    assert_result_count(
        ds.subdatasets(), 1, path=sub.path, state='present')
    # uninstall the subdataset
    ds.drop('sub', what='all', reckless='kill', recursive=True)
    # normal 'gone' is "absent"
    assert_false(sub.is_installed())
    assert_result_count(
        ds.subdatasets(), 1, path=sub.path, state='absent')
    # with directory totally gone also
    os.rmdir(sub.path)
    assert_result_count(
        ds.subdatasets(), 1, path=sub.path, state='absent')
    # putting dir back, no change
    os.makedirs(sub.path)
    assert_result_count(
        ds.subdatasets(), 1, path=sub.path, state='absent')


@with_tempfile
def test_get_subdatasets_types(path=None):
    ds = create(path)
    ds.create('1')
    ds.create('true')
    # no types casting should happen
    eq_(ds.subdatasets(result_xfm='relpaths'), ['1', 'true'])


@with_tempfile
def test_parent_on_unborn_branch(path=None):
    from datalad.support.gitrepo import GitRepo
    ds = Dataset(GitRepo(path, create=True).path)
    assert_false(ds.repo.get_hexsha())

    subrepo = GitRepo(opj(path, "sub"), create=True)
    subrepo.commit(msg="c", options=["--allow-empty"])

    ds.repo.save(path="sub")
    eq_(ds.subdatasets(result_xfm='relpaths'),
        ["sub"])


@with_tempfile
@with_tempfile
def test_name_starts_with_hyphen(origpath=None, path=None):
    ds = Dataset.create(origpath)
    # create
    dash_sub = ds.create('-sub')
    assert_true(dash_sub.is_installed())
    assert_result_count(
        ds.subdatasets(), 1, path=dash_sub.path, state='present')

    # clone
    ds_clone = Dataset.create(path)
    dash_clone = clone(source=dash_sub.path, path=os.path.join(path, '-clone'))
    ds_clone.save(recursive=True)
    assert_true(dash_clone.is_installed())
    assert_result_count(
        ds_clone.subdatasets(), 1, path=dash_clone.path, state='present')

    # uninstall
    ds_clone.drop('-clone', what='all', reckless='kill', recursive=True)
    assert_false(dash_clone.is_installed())
    assert_result_count(
        ds_clone.subdatasets(), 1, path=dash_clone.path, state='absent')

    # get
    ds_clone.get('-clone')
    assert_true(dash_clone.is_installed())
    assert_result_count(
        ds_clone.subdatasets(), 1, path=dash_clone.path, state='present')

    assert_repo_status(ds.path)
