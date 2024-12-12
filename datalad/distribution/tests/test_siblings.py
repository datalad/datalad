# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test adding sibling(s) to a dataset

"""

import pytest

from datalad.api import (
    Dataset,
    clone,
    create,
    install,
    siblings,
)
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.support.path import basename
from datalad.support.path import join as opj
from datalad.support.path import (
    normpath,
    relpath,
)
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_result_count,
    assert_status,
    chpwd,
    create_tree,
    eq_,
    ok_,
    on_appveyor,
    serve_path_via_http,
    with_sameas_remote,
    with_tempfile,
)
from datalad.utils import (
    Path,
    on_windows,
)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_siblings(origin=None, repo_path=None, local_clone_path=None):
    ca = dict(result_renderer='disabled')
    # a remote dataset with a subdataset underneath
    origds = Dataset(origin).create(**ca)
    _ = origds.create('subm 1', **ca)

    sshurl = "ssh://push-remote.example.com"
    httpurl1 = "http://remote1.example.com/location"
    httpurl2 = "http://remote2.example.com/location"

    # insufficient arguments
    # we need a dataset to work at
    with chpwd(repo_path):  # not yet there
        assert_raises(InsufficientArgumentsError,
                      siblings, 'add', url=httpurl1, **ca)

    # prepare src
    source = install(repo_path, source=origin, recursive=True, **ca)
    # pollute config
    depvar = 'remote.test-remote.datalad-publish-depends'
    source.config.add(depvar, 'stupid', scope='local')

    # cannot configure unknown remotes as dependencies
    res = siblings(
        'configure',
        dataset=source,
        name="test-remote",
        url=httpurl1,
        publish_depends=['r1', 'r2'],
        on_failure='ignore',
        **ca)
    assert_status('error', res)
    eq_(res[0]['message'],
        ('unknown sibling(s) specified as publication dependency: %s',
         set(('r1', 'r2'))))
    # prior config was not changed by failed call above
    eq_(source.config.get(depvar, None), 'stupid')

    res = siblings('configure',
                   dataset=source, name="test-remote",
                   url=httpurl1,
                   result_xfm='paths',
                   **ca)

    eq_(res, [source.path])
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))

    # reconfiguring doesn't change anything
    siblings('configure', dataset=source, name="test-remote",
             url=httpurl1, **ca)
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))
    # re-adding doesn't work
    res = siblings('add', dataset=source, name="test-remote",
                   url=httpurl1, on_failure='ignore', **ca)
    assert_status('error', res)
    # only after removal
    res = siblings('remove', dataset=source, name="test-remote", **ca)
    assert_status('ok', res)
    assert_not_in("test-remote", source.repo.get_remotes())
    # remove again (with result renderer to smoke-test a renderer
    # special case for this too)
    res = siblings('remove', dataset=source, name="test-remote", **ca)
    assert_status('notneeded', res)

    res = siblings('add', dataset=source, name="test-remote",
                   url=httpurl1, on_failure='ignore', **ca)
    assert_status('ok', res)

    # add another remove with a publication dependency
    # again pre-pollute config
    depvar = 'remote.test-remote2.datalad-publish-depends'
    pushvar = 'remote.test-remote2.push'
    source.config.add(depvar, 'stupid', scope='local')
    source.config.add(pushvar, 'senseless', scope='local')
    res = siblings('configure', dataset=source, name="test-remote2",
                   url=httpurl2, on_failure='ignore',
                   publish_depends='test-remote',
                   # just for smoke testing
                   publish_by_default=DEFAULT_BRANCH,
                   **ca)
    assert_status('ok', res)
    # config replaced with new setup
    #source.config.reload(force=True)
    eq_(source.config.get(depvar, None), 'test-remote')
    eq_(source.config.get(pushvar, None), DEFAULT_BRANCH)

    # add to another remote automagically taking it from the url
    # and being in the dataset directory
    with chpwd(source.path):
        res = siblings('add', url=httpurl2, **ca)
    assert_result_count(
        res, 1,
        name="remote2.example.com", type='sibling')
    assert_in("remote2.example.com", source.repo.get_remotes())

    # don't fail with conflicting url, when using force:
    res = siblings('configure',
                   dataset=source, name="test-remote",
                   url=httpurl1 + "/elsewhere",
                   **ca)
    assert_status('ok', res)
    eq_(httpurl1 + "/elsewhere",
        source.repo.get_remote_url("test-remote"))

    # no longer a use case, I would need additional convincing that
    # this is anyhow useful other then triple checking other peoples
    # errors. for an actual check use 'query'
    # maybe it could be turned into a set of warnings when `configure`
    # alters an existing setting, but then why call configure, if you
    # want to keep the old values
    #with assert_raises(RuntimeError) as cm:
    #    add_sibling(dataset=source, name="test-remote",
    #                url=httpurl1 + "/elsewhere")
    #assert_in("""'test-remote' already exists with conflicting settings""",
    #          str(cm.value))
    ## add a push url without force fails, since in a way the fetch url is the
    ## configured push url, too, in that case:
    #with assert_raises(RuntimeError) as cm:
    #    add_sibling(dataset=source, name="test-remote",
    #                url=httpurl1 + "/elsewhere",
    #                pushurl=sshurl, force=False)
    #assert_in("""'test-remote' already exists with conflicting settings""",
    #          str(cm.value))

    # add push url (force):
    res = siblings('configure',
                   dataset=source, name="test-remote",
                   url=httpurl1 + "/elsewhere",
                   pushurl=sshurl,
                   **ca)
    assert_status('ok', res)
    eq_(httpurl1 + "/elsewhere",
        source.repo.get_remote_url("test-remote"))
    eq_(sshurl,
        source.repo.get_remote_url("test-remote", push=True))

    # recursively:
    for r in siblings(
            'configure',
            dataset=source, name="test-remote",
            url=httpurl1 + "/%NAME",
            pushurl=sshurl + "/%NAME",
            recursive=True,
            # we need to disable annex queries, as it will try to access
            # the fake URL configured above
            get_annex_info=False,
            **ca):
        repo = GitRepo(r['path'], create=False)
        assert_in("test-remote", repo.get_remotes())
        url = repo.get_remote_url("test-remote")
        pushurl = repo.get_remote_url("test-remote", push=True)
        ok_(url.startswith(httpurl1 + '/' + basename(source.path)))
        ok_(url.endswith(basename(repo.path)))
        ok_(pushurl.startswith(sshurl + '/' + basename(source.path)))
        ok_(pushurl.endswith(basename(repo.path)))
        eq_(url, r['url'])
        eq_(pushurl, r['pushurl'])

    # recursively without template:
    for r in siblings(
            'configure',
            dataset=source, name="test-remote-2",
            url=httpurl1,
            pushurl=sshurl,
            recursive=True,
            # we need to disable annex queries, as it will try to access
            # the fake URL configured above
            get_annex_info=False,
            **ca):
        repo = GitRepo(r['path'], create=False)
        assert_in("test-remote-2", repo.get_remotes())
        url = repo.get_remote_url("test-remote-2")
        pushurl = repo.get_remote_url("test-remote-2", push=True)
        ok_(url.startswith(httpurl1))
        ok_(pushurl.startswith(sshurl))
        # FIXME: next condition used to compare the *Repo objects instead of
        # there paths. Due to missing annex-init in
        # datalad/tests/utils.py:clone_url this might not be the same, since
        # `source` actually is an annex, but after flavor 'clone' in
        # `with_testrepos` and then `install` any trace of an annex might be
        # gone in v5 (branch 'master' only), while in direct mode it still is
        # considered an annex. `repo` is forced to be a `GitRepo`, so we might
        # compare two objects of different classes while they actually are
        # pointing to the same repository.
        # See github issue #1854
        if repo.path != source.repo.path:
            ok_(url.endswith('/' + basename(repo.path)))
            ok_(pushurl.endswith(basename(repo.path)))
        eq_(url, r['url'])
        eq_(pushurl, r['pushurl'])

    # recursively without template and pushurl but full "hierarchy"
    # to a local clone
    for r in siblings(
            'configure',
            dataset=source,
            name="test-remote-3",
            url=local_clone_path,
            recursive=True,
            # we need to disable annex queries, as it will try to access
            # the fake URL configured above
            get_annex_info=False,
            **ca):
        repo = GitRepo(r['path'], create=False)
        assert_in("test-remote-3", repo.get_remotes())
        url = repo.get_remote_url("test-remote-3")
        pushurl = repo.get_remote_url("test-remote-3", push=True)

        eq_(normpath(url),
            normpath(opj(local_clone_path,
                         relpath(str(r['path']), source.path))))
        # https://github.com/datalad/datalad/issues/3951
        ok_(not pushurl)  # no pushurl should be defined
    # 5621: Users shouldn't pass identical names for remote & common data source
    assert_raises(ValueError, siblings, 'add', dataset=source, name='howdy',
                  url=httpurl1, as_common_datasrc='howdy')


@with_tempfile(mkdir=True)
def test_here(path=None):
    # few smoke tests regarding the 'here' sibling
    ds = create(path)
    res = ds.siblings(
        'query',
        on_failure='ignore',
        result_renderer='disabled')
    assert_status('ok', res)
    assert_result_count(res, 1)
    assert_result_count(res, 1, name='here')
    here = res[0]
    eq_(ds.repo.uuid, here['annex-uuid'])
    assert_in('annex-description', here)
    assert_in('annex-bare', here)
    assert_in('available_local_disk_space', here)

    # unknown sibling query errors
    res = ds.siblings(
        'query',
        name='notthere',
        on_failure='ignore',
        result_renderer='disabled')
    assert_status('error', res)

    # set a description
    res = ds.siblings(
        'configure',
        name='here',
        description='very special',
        on_failure='ignore',
        result_renderer='disabled')
    assert_status('ok', res)
    assert_result_count(res, 1)
    assert_result_count(res, 1, name='here')
    here = res[0]
    eq_('very special', here['annex-description'])

    # does not die when here is dead
    res = ds.siblings('query', name='here', return_type='item-or-list')
    # gone when dead
    res.pop('annex-description', None)
    # volatile prop
    res.pop('available_local_disk_space', None)
    ds.repo.call_annex(['dead', 'here'])
    newres = ds.siblings('query', name='here', return_type='item-or-list')
    newres.pop('available_local_disk_space', None)
    eq_(res, newres)


@with_tempfile(mkdir=True)
def test_no_annex(path=None):
    # few smoke tests regarding the 'here' sibling
    ds = create(path, annex=False)
    res = ds.siblings(
        'configure',
        name='here',
        description='very special',
        on_failure='ignore',
        result_renderer='disabled')
    assert_status('impossible', res)

    res = ds.siblings(
        'enable',
        name='doesnotmatter',
        on_failure='ignore',
        result_renderer='disabled')
    assert_in_results(
        res, status='impossible',
        message='cannot enable sibling of non-annex dataset')


@with_tempfile()
@with_tempfile()
def test_arg_missing(path=None, path2=None):
    # test fix for gh-3553
    ds = create(path)
    assert_raises(
        InsufficientArgumentsError,
        ds.siblings,
        'add',
        url=path2,
    )
    assert_status(
        'ok',
        ds.siblings(
            'add', url=path2, name='somename'))
    # trigger some name guessing functionality that will still not
    # being able to end up using a hostnames-spec despite being
    # given a URL
    if not on_windows:
        # the trick with the file:// URL creation only works on POSIX
        # the underlying tested code here is not about paths, though,
        # so it is good enough to run this on POSIX system to be
        # reasonably sure that things work
        assert_raises(
            InsufficientArgumentsError,
            ds.siblings,
            'add',
            url=f'file://{path2}',
        )

    # there is no name guessing with 'configure'
    assert_in_results(
        ds.siblings('configure', url='http://somename', on_failure='ignore'),
        status='error',
        message='need sibling `name` for configuration')

    # needs a URL
    assert_raises(
        InsufficientArgumentsError, ds.siblings, 'add', name='somename')
    # just pushurl is OK
    assert_status('ok', ds.siblings('add', pushurl=path2, name='somename2'))

    # needs group with groupwanted
    assert_raises(
        InsufficientArgumentsError,
        ds.siblings, 'add', url=path2, name='somename',
        annex_groupwanted='whatever')


@with_sameas_remote
@with_tempfile(mkdir=True)
def test_sibling_enable_sameas(repo=None, clone_path=None):
    ds = Dataset(repo.path)
    create_tree(ds.path, {"f0": "0"})
    ds.save(path="f0")
    ds.push(["f0"], to="r_dir")
    ds.repo.drop(["f0"])

    ds_cloned = clone(ds.path, clone_path)

    assert_false(ds_cloned.repo.file_has_content("f0"))
    # does not work without a name
    res = ds_cloned.siblings(
        action="enable",
        result_renderer='disabled',
        on_failure='ignore',
    )
    assert_in_results(
        res, status='error', message='require `name` of sibling to enable')
    # does not work with the wrong name
    res = ds_cloned.siblings(
        action="enable",
        name='wrong',
        result_renderer='disabled',
        on_failure='ignore',
    )
    assert_in_results(
        res, status='impossible',
        message=("cannot enable sibling '%s', not known", 'wrong')
    )
    # works with the right name
    res = ds_cloned.siblings(action="enable", name="r_rsync")
    assert_status("ok", res)
    ds_cloned.get(path=["f0"])
    ok_(ds_cloned.repo.file_has_content("f0"))


@with_tempfile(mkdir=True)
def test_sibling_inherit(basedir=None):
    ds_source = Dataset(opj(basedir, "source")).create()

    # In superdataset, set up remote "source" that has git-annex group "grp".
    ds_super = Dataset(opj(basedir, "super")).create()
    ds_super.siblings(action="add", name="source", url=ds_source.path,
                      annex_group="grp", result_renderer='disabled')

    ds_clone = ds_super.clone(
        source=ds_source.path, path="clone")
    # In a subdataset, adding a "source" sibling with inherit=True pulls in
    # that configuration.
    ds_clone.siblings(action="add", name="source", url=ds_source.path,
                      inherit=True, result_renderer='disabled')
    res = ds_clone.siblings(action="query", name="source",
                            result_renderer='disabled')
    eq_(res[0]["annex-group"], "grp")


@with_tempfile(mkdir=True)
def test_sibling_inherit_no_super_remote(basedir=None):
    ds_source = Dataset(opj(basedir, "source")).create()
    ds_super = Dataset(opj(basedir, "super")).create()
    ds_clone = ds_super.clone(
        source=ds_source.path, path="clone")
    # Adding a sibling with inherit=True doesn't crash when the superdataset
    # doesn't have a remote `name`.
    ds_clone.siblings(action="add", name="donotexist", inherit=True,
                      url=ds_source.path, result_renderer='disabled')


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_sibling_path_is_posix(basedir=None, otherpath=None):
    ds_source = Dataset(opj(basedir, "source")).create()
    # add remote with system native path
    ds_source.siblings(
        action="add",
        name="donotexist",
        url=otherpath,
        result_renderer='disabled')
    res = ds_source.siblings(
        action="query",
        name="donotexist",
        result_renderer='disabled',
        return_type='item-or-list')
    # path URL should come out POSIX as if `git clone` had configured it for origin
    # https://github.com/datalad/datalad/issues/3972
    eq_(res['url'], Path(otherpath).as_posix())


@with_tempfile()
def test_bf3733(path=None):
    ds = create(path)
    # call siblings configure for an unknown sibling without a URL
    # doesn't work, but also doesn't crash
    assert_result_count(
        ds.siblings(
            'configure',
            name='imaginary',
            publish_depends='doesntmatter',
            url=None,
            on_failure='ignore'),
        1,
        status='error',
        action="configure-sibling",
        name="imaginary",
        path=ds.path,
    )


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@serve_path_via_http
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_as_common_datasource(testbed=None, viapath=None, viaurl=None,
                              remotepath=None, url=None, remotepath2=None, url2=None):
    ds = Dataset(remotepath).create()
    (ds.pathobj / 'testfile').write_text('likemagic')
    (ds.pathobj / 'testfile2').write_text('likemagic2')
    ds.save()

    # make clonable via HTTP
    ds.repo.call_git(['update-server-info'])

    # populate location of the 2nd url, so we have two remotes with different UUIDs
    ds2 = clone(source=remotepath, path=remotepath2)
    ds2.get('testfile')
    ds2.repo.call_git(['update-server-info'])

    # this does not work for remotes that have path URLs
    ds_frompath = clone(source=remotepath, path=viapath)
    res = ds_frompath.siblings(
        'configure',
        name=DEFAULT_REMOTE,
        as_common_datasrc='mike',
        on_failure='ignore',
        result_renderer='disabled',
    )
    assert_in_results(
        res,
        status='impossible',
        message='cannot configure as a common data source, URL protocol '
                'is not http or https',
    )

    # but it works for HTTP
    ds_fromurl = clone(source=url, path=viaurl)
    res = ds_fromurl.siblings(
        'configure',
        name=DEFAULT_REMOTE,
        as_common_datasrc='mike2',
        result_renderer='disabled',
    )
    assert_status('ok', res)

    # same thing should be possible by adding a fresh remote
    # We need to do it on a different URL since some versions of git-annex
    # such as 10.20220322-1~ndall+1 might refuse operate with multiple remotes
    # with identical URLs, and otherwise just reuse the same UUID/remote
    res = ds_fromurl.siblings(
        'add',
        name='fresh',
        # we must amend the URL given by serve_path_via_http, because
        # we are serving the root of a non-bare repository, but git-annex
        # needs to talk to its .git (git-clone would also not eat
        # `url` unmodified).
        url=url2 + '.git',
        as_common_datasrc='fresh-sr',
        result_renderer='disabled',
    )
    assert_status('ok', res)

    # now try if it works. we will clone the clone, and get a repo that does
    # not know its ultimate origin. still, we should be able to pull data
    # from it via the special remote
    testbed = clone(source=ds_fromurl, path=testbed)
    assert_status('ok', testbed.get('testfile'))
    eq_('likemagic', (testbed.pathobj / 'testfile').read_text())
    # and the other one
    assert_status('ok', testbed.get('testfile2'))

    # Let's get explicitly from both remotes which would not work if URL
    # above is wrong or one of the remotes not autoenabled
    for remote in 'mike2', 'fresh-sr':
        assert_status('ok', testbed.drop('testfile'))
        assert_status('ok', testbed.get('testfile', source=remote))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_specialremote(dspath=None, remotepath=None):
    ds = Dataset(dspath).create()
    ds.repo.call_annex(
        ['initremote', 'myremote', 'type=directory',
         f'directory={remotepath}', 'encryption=none'])
    res = ds.siblings('query', result_renderer='disabled')
    assert_in_results(
        res,
        **{'name': 'myremote',
           'annex-type': 'directory',
           'annex-directory': remotepath})
