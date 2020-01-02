# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test adding sibling(s) to a dataset

"""

from datalad.support.path import (
    basename,
    join as opj,
    normpath,
    relpath,
)

from datalad.api import (
    clone,
    create,
    Dataset,
    install,
    siblings,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import InsufficientArgumentsError

from datalad.tests.utils import (
    chpwd,
    create_tree,
    with_tempfile, with_testrepos,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_status,
    assert_result_count,
    with_sameas_remote,
    eq_,
    ok_,
)

from datalad.utils import Path


# work on cloned repos to be safer
@with_testrepos('submodule_annex', flavors=['clone'])
@with_tempfile(mkdir=True)
@with_tempfile
def test_siblings(origin, repo_path, local_clone_path):

    sshurl = "ssh://push-remote.example.com"
    httpurl1 = "http://remote1.example.com/location"
    httpurl2 = "http://remote2.example.com/location"

    # insufficient arguments
    # we need a dataset to work at
    with chpwd(repo_path):  # not yet there
        assert_raises(InsufficientArgumentsError,
                      siblings, 'add', url=httpurl1)

    # prepare src
    source = install(repo_path, source=origin, recursive=True)
    # pollute config
    depvar = 'remote.test-remote.datalad-publish-depends'
    source.config.add(depvar, 'stupid', where='local')

    # cannot configure unknown remotes as dependencies
    res = siblings(
        'configure',
        dataset=source,
        name="test-remote",
        url=httpurl1,
        publish_depends=['r1', 'r2'],
        on_failure='ignore',
        result_renderer=None)
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
                   result_renderer=None)

    eq_(res, [source.path])
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))

    # reconfiguring doesn't change anything
    siblings('configure', dataset=source, name="test-remote",
             url=httpurl1,
             result_renderer=None)
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))
    # re-adding doesn't work
    res = siblings('add', dataset=source, name="test-remote",
                   url=httpurl1, on_failure='ignore',
                   result_renderer=None)
    assert_status('error', res)
    # only after removal
    res = siblings('remove', dataset=source, name="test-remote",
                   result_renderer=None)
    assert_status('ok', res)
    assert_not_in("test-remote", source.repo.get_remotes())
    res = siblings('add', dataset=source, name="test-remote",
                   url=httpurl1, on_failure='ignore',
                   result_renderer=None)
    assert_status('ok', res)

    # add to another remote automagically taking it from the url
    # and being in the dataset directory
    with chpwd(source.path):
        res = siblings('add', url=httpurl2,
                       result_renderer=None)
    assert_result_count(
        res, 1,
        name="remote2.example.com", type='sibling')
    assert_in("remote2.example.com", source.repo.get_remotes())

    # don't fail with conflicting url, when using force:
    res = siblings('configure',
                   dataset=source, name="test-remote",
                   url=httpurl1 + "/elsewhere",
                   result_renderer=None)
    assert_status('ok', res)
    eq_(httpurl1 + "/elsewhere",
        source.repo.get_remote_url("test-remote"))

    # no longer a use case, I would need additional convincing that
    # this is anyhow useful other then tripple checking other peoples
    # errors. for an actual check use 'query'
    # maybe it could be turned into a set of warnings when `configure`
    # alters an existing setting, but then why call configure, if you
    # want to keep the old values
    #with assert_raises(RuntimeError) as cm:
    #    add_sibling(dataset=source, name="test-remote",
    #                url=httpurl1 + "/elsewhere")
    #assert_in("""'test-remote' already exists with conflicting settings""",
    #          str(cm.exception))
    ## add a push url without force fails, since in a way the fetch url is the
    ## configured push url, too, in that case:
    #with assert_raises(RuntimeError) as cm:
    #    add_sibling(dataset=source, name="test-remote",
    #                url=httpurl1 + "/elsewhere",
    #                pushurl=sshurl, force=False)
    #assert_in("""'test-remote' already exists with conflicting settings""",
    #          str(cm.exception))

    # add push url (force):
    res = siblings('configure',
                   dataset=source, name="test-remote",
                   url=httpurl1 + "/elsewhere",
                   pushurl=sshurl,
                   result_renderer=None)
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
            get_annex_info=False):
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
            result_renderer=None):
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
            result_renderer=None):
        repo = GitRepo(r['path'], create=False)
        assert_in("test-remote-3", repo.get_remotes())
        url = repo.get_remote_url("test-remote-3")
        pushurl = repo.get_remote_url("test-remote-3", push=True)

        eq_(normpath(url),
            normpath(opj(local_clone_path,
                         relpath(str(r['path']), source.path))))
        # https://github.com/datalad/datalad/issues/3951
        ok_(not pushurl)  # no pushurl should be defined

@with_tempfile(mkdir=True)
def test_here(path):
    # few smoke tests regarding the 'here' sibling
    ds = create(path)
    res = ds.siblings(
        'query',
        on_failure='ignore',
        result_renderer=None)
    assert_status('ok', res)
    assert_result_count(res, 1)
    assert_result_count(res, 1, name='here')
    here = res[0]
    eq_(ds.repo.uuid, here['annex-uuid'])
    assert_in('annex-description', here)
    assert_in('annex-bare', here)
    assert_in('available_local_disk_space', here)

    # set a description
    res = ds.siblings(
        'configure',
        name='here',
        description='very special',
        on_failure='ignore',
        result_renderer=None)
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
    ds.repo._run_annex_command('dead', annex_options=['here'])
    newres = ds.siblings('query', name='here', return_type='item-or-list')
    newres.pop('available_local_disk_space', None)
    eq_(res, newres)


@with_tempfile()
@with_tempfile()
def test_arg_missing(path, path2):
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


@with_sameas_remote
@with_tempfile(mkdir=True)
def test_sibling_enable_sameas(repo, clone_path):
    ds = Dataset(repo.path)
    create_tree(ds.path, {"f0": "0"})
    ds.save(path="f0")
    ds.repo.copy_to(["f0"], remote="r_dir")
    ds.repo.drop(["f0"])

    ds_cloned = clone(ds.path, clone_path)

    assert_false(ds_cloned.repo.file_has_content("f0"))
    res = ds_cloned.siblings(action="enable", name="r_rsync")
    assert_status("ok", res)
    ds_cloned.get(path=["f0"])
    ok_(ds_cloned.repo.file_has_content("f0"))


@with_tempfile(mkdir=True)
def test_sibling_inherit(basedir):
    ds_source = Dataset(opj(basedir, "source")).create()

    # In superdataset, set up remote "source" that has git-annex group "grp".
    ds_super = Dataset(opj(basedir, "super")).create()
    ds_super.siblings(action="add", name="source", url=ds_source.path,
                      annex_group="grp", result_renderer=None)

    ds_clone = ds_super.clone(
        source=ds_source.path, path="clone")
    # In a subdataset, adding a "source" sibling with inherit=True pulls in
    # that configuration.
    ds_clone.siblings(action="add", name="source", url=ds_source.path,
                      inherit=True, result_renderer=None)
    res = ds_clone.siblings(action="query", name="source",
                            result_renderer=None)
    eq_(res[0]["annex-group"], "grp")


@with_tempfile(mkdir=True)
def test_sibling_inherit_no_super_remote(basedir):
    ds_source = Dataset(opj(basedir, "source")).create()
    ds_super = Dataset(opj(basedir, "super")).create()
    ds_clone = ds_super.clone(
        source=ds_source.path, path="clone")
    # Adding a sibling with inherit=True doesn't crash when the superdataset
    # doesn't have a remote `name`.
    ds_clone.siblings(action="add", name="donotexist", inherit=True,
                      url=ds_source.path, result_renderer=None)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_sibling_path_is_posix(basedir, otherpath):
    ds_source = Dataset(opj(basedir, "source")).create()
    # add remote with system native path
    ds_source.siblings(
        action="add",
        name="donotexist",
        url=otherpath,
        result_renderer=None)
    res = ds_source.siblings(
        action="query",
        name="donotexist",
        result_renderer=None,
        return_type='item-or-list')
    # path URL should come out POSIX as if `git clone` had configured it for origin
    # https://github.com/datalad/datalad/issues/3972
    eq_(res['url'], Path(otherpath).as_posix())
     
