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

import pytest

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


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_by_property(path=None):
    """Test --r-filter with custom .gitmodules properties"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')
    sub3 = ds.create('sub3')
    # set custom properties on sub1 and sub2
    ds.subdatasets(set_property=[('mytag', 'core')], path='sub1')
    ds.subdatasets(set_property=[('mytag', 'extra')], path='sub2')
    # sub3 has no mytag

    # filter for mytag=core
    res = ds.subdatasets(recursion_filter=['mytag=core'],
                         result_xfm='relpaths')
    eq_(res, ['sub1'])

    # filter for mytag!=core -> sub2 (sub3 has no mytag so doesn't match !=)
    res = ds.subdatasets(recursion_filter=['mytag!=core'],
                         result_xfm='relpaths')
    eq_(res, ['sub2'])

    # filter for mytag? (exists)
    res = ds.subdatasets(recursion_filter=['mytag?'],
                         result_xfm='relpaths')
    eq_(res, ['sub1', 'sub2'])

    # filter for mytag!? (not exists)
    res = ds.subdatasets(recursion_filter=['mytag!?'],
                         result_xfm='relpaths')
    eq_(res, ['sub3'])


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_by_state(path=None):
    """Test --r-filter with .state internal property"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')
    assert_repo_status(ds.path)

    # both present
    res = ds.subdatasets(recursion_filter=['.state=present'],
                         result_xfm='relpaths')
    eq_(res, ['sub1', 'sub2'])

    res = ds.subdatasets(recursion_filter=['.state=absent'],
                         result_xfm='relpaths')
    eq_(res, [])


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_url_regex(path=None):
    """Test --r-filter with regex on URL"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')

    # Get the URLs
    all_subs = ds.subdatasets()
    # Both have local URLs; test regex on url
    # filter for url matching 'sub1'
    res = ds.subdatasets(recursion_filter=['url~=sub1'],
                         result_xfm='relpaths')
    eq_(res, ['sub1'])

    # filter for url NOT matching 'sub1'
    res = ds.subdatasets(recursion_filter=['url!~sub1'],
                         result_xfm='relpaths')
    eq_(res, ['sub2'])


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_multiple_and(path=None):
    """Test that multiple --r-filter expressions are ANDed"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')
    ds.subdatasets(set_property=[('group', 'core')], path='sub1')
    ds.subdatasets(set_property=[('group', 'core')], path='sub2')
    ds.subdatasets(set_property=[('priority', 'high')], path='sub1')
    ds.subdatasets(set_property=[('priority', 'low')], path='sub2')

    # both have group=core
    res = ds.subdatasets(recursion_filter=['group=core'],
                         result_xfm='relpaths')
    eq_(res, ['sub1', 'sub2'])

    # AND with priority=high -> only sub1
    res = ds.subdatasets(recursion_filter=['group=core', 'priority=high'],
                         result_xfm='relpaths')
    eq_(res, ['sub1'])


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_recursive(path=None):
    """Test --r-filter works recursively into nested subdatasets"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')
    subsub = sub1.create('subsub')
    ds.save(recursive=True)

    # Set tag=include on sub1 and subsub, but not sub2
    ds.subdatasets(set_property=[('tag', 'include')], path='sub1')
    sub1.subdatasets(set_property=[('tag', 'include')], path='subsub')
    sub1.save()
    ds.save()

    # recursive query with tag=include should get sub1 and subsub
    # (sub2 is skipped, and sub1 matches so recursion enters it)
    res = ds.subdatasets(recursive=True,
                         recursion_filter=['tag=include'],
                         result_xfm='relpaths')
    eq_(res, ['sub1', _p('sub1/subsub')])

    # filter that only matches top-level sub1: subsub is also visited
    # because sub1 passes, but subsub also needs to match to be reported.
    # Set a different property on sub1 only
    ds.subdatasets(set_property=[('level', 'top')], path='sub1')
    ds.save()

    res = ds.subdatasets(recursive=True,
                         recursion_filter=['level=top'],
                         result_xfm='relpaths')
    # sub1 matches, sub2 doesn't. sub1/subsub also doesn't have level=top.
    eq_(res, ['sub1'])

    # If parent is filtered out, we never recurse into its children
    ds.subdatasets(set_property=[('tag', 'exclude')], path='sub1')
    ds.save()

    res = ds.subdatasets(recursive=True,
                         recursion_filter=['tag=exclude'],
                         result_xfm='relpaths')
    # sub1 matches; subsub has tag=include, not tag=exclude
    eq_(res, ['sub1'])


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_no_filter(path=None):
    """Passing no filter should return everything (same as without param)"""
    ds = Dataset(path).create()
    ds.create('sub1')
    ds.create('sub2')

    all_subs = ds.subdatasets(result_xfm='relpaths')
    filtered_subs = ds.subdatasets(recursion_filter=None,
                                   result_xfm='relpaths')
    eq_(all_subs, filtered_subs)


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_relative_url_in_tree(path=None):
    """Test .relative-url-in-tree computed property for BIDS-style interlinks"""
    import subprocess
    ds = Dataset(path).create()
    # Create source dataset at sourcedata/raw
    sourcedata = ds.create(opj('sourcedata', 'raw'))
    # Create derivatives subdataset
    deriv = ds.create(opj('derivatives', 'sub1'))
    # Add sourcedata/raw as a subdataset of derivatives/sub1 with a
    # relative URL pointing to ../../sourcedata/raw (the BIDS pattern)
    subprocess.run(
        ['git', '-c', 'protocol.file.allow=always',
         'submodule', 'add', '../../sourcedata/raw', 'input'],
        cwd=str(deriv.pathobj),
        check=True,
    )
    # save changes in derivatives/sub1 (records the new submodule)
    deriv.save(message='add input submodule with relative URL')
    # save top-level non-recursively — recursive save would try to
    # resolve branches inside the nested input submodule which fails
    # on adjusted-branch filesystems (CrippledFS) where the corresponding
    # regular branch may not exist locally (gh-7820)
    ds.save(message='save all')

    # First, without filter, confirm recursive query sees all 3 subdatasets
    all_res = ds.subdatasets(recursive=True)
    eq_(len(all_res), 3)  # sourcedata/raw, derivatives/sub1, input

    # Top-level subs (sourcedata/raw, derivatives/sub1) were created by
    # datalad create, which uses relative URLs (./sourcedata/raw,
    # ./derivatives/sub1) that resolve within the tree → 'present'.
    # The interlinked "input" sub also has a relative URL → 'present'.
    res_present = ds.subdatasets(
        recursive=True,
        recursion_filter=['.relative-url-in-tree=present'])
    paths_present = [r['path'] for r in res_present]
    assert str(sourcedata.pathobj) in paths_present
    assert str(deriv.pathobj) in paths_present
    assert str(deriv.pathobj / 'input') in paths_present

    # Filter for false should find nothing since all URLs are relative
    # and resolve within the tree
    res_false = ds.subdatasets(
        recursive=True,
        recursion_filter=['.relative-url-in-tree=false'])
    assert_result_count(res_false, 0)


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_relative_url_outside_tree(path=None):
    """Test that relative URLs pointing outside the tree yield 'false'"""
    ds = Dataset(path).create()
    sub = ds.create('sub')
    # Test the function directly with synthetic records
    from datalad.local.subdatasets import (
        RelativeUrlInTree,
        _compute_relative_url_in_tree,
    )

    # simulate a record with URL pointing outside tree
    sm = {
        'path': sub.pathobj / 'external',
        'gitmodule_url': '../../outside_tree',
    }
    result = _compute_relative_url_in_tree(sm, sub.pathobj, ds.pathobj)
    assert result is RelativeUrlInTree.FALSE

    # simulate a record with an absolute URL
    sm_abs = {
        'path': sub.pathobj / 'external',
        'gitmodule_url': 'https://github.com/example/repo.git',
    }
    result_abs = _compute_relative_url_in_tree(sm_abs, sub.pathobj, ds.pathobj)
    assert result_abs is RelativeUrlInTree.FALSE

    # simulate a record with an absolute file path
    sm_abs_path = {
        'path': sub.pathobj / 'external',
        'gitmodule_url': '/absolute/path/to/repo',
    }
    result_abs_path = _compute_relative_url_in_tree(
        sm_abs_path, sub.pathobj, ds.pathobj)
    assert result_abs_path is RelativeUrlInTree.FALSE


@pytest.mark.ai_generated
@with_tempfile
def test_subdatasets_r_filter_config(path=None):
    """Test datalad.recursion.filter config default"""
    ds = Dataset(path).create()
    sub1 = ds.create('sub1')
    sub2 = ds.create('sub2')
    # set a custom property
    ds.subdatasets(set_property=[('group', 'core')], path='sub1')

    # without config, get both
    all_subs = ds.subdatasets(result_xfm='relpaths')
    eq_(len(all_subs), 2)

    # set config filter
    ds.config.set('datalad.recursion.filter', 'group=core', scope='local')

    # now subdatasets should filter by default
    filtered = ds.subdatasets(result_xfm='relpaths')
    eq_(filtered, [_p('sub1')])

    # CLI recursion_filter should AND with config
    # group=core AND .state=present => still sub1
    filtered2 = ds.subdatasets(
        recursion_filter=['.state=present'], result_xfm='relpaths')
    eq_(filtered2, [_p('sub1')])

    # filter that conflicts => no results
    filtered3 = ds.subdatasets(
        recursion_filter=['group=nonexistent'], result_xfm='relpaths')
    eq_(filtered3, [])

    # unset config, back to normal
    ds.config.unset('datalad.recursion.filter', scope='local')
    all_again = ds.subdatasets(result_xfm='relpaths')
    eq_(len(all_again), 2)
