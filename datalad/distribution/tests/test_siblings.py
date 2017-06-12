# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test adding sibling(s) to a dataset

"""

from os.path import join as opj, basename
from datalad.api import create
from datalad.api import install
from datalad.api import siblings
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import InsufficientArgumentsError

from datalad.tests.utils import chpwd
from datalad.tests.utils import with_tempfile, with_testrepos
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count

from nose.tools import eq_, ok_


# work on cloned repos to be safer
@with_testrepos('submodule_annex', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_siblings(origin, repo_path):

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
    assert_in('unknown sibling(s) specified as publication dependency',
              res[0]['message'])
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
            result_renderer=None):
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
            result_renderer=None):
        repo = GitRepo(r['path'], create=False)
        assert_in("test-remote-2", repo.get_remotes())
        url = repo.get_remote_url("test-remote-2")
        pushurl = repo.get_remote_url("test-remote-2", push=True)
        ok_(url.startswith(httpurl1))
        ok_(pushurl.startswith(sshurl))
        if repo != source.repo:
            ok_(url.endswith('/' + basename(repo.path)))
            ok_(pushurl.endswith(basename(repo.path)))
        eq_(url, r['url'])
        eq_(pushurl, r['pushurl'])


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
