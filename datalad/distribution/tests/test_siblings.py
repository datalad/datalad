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
from datalad.api import install, add_sibling
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import InsufficientArgumentsError

from datalad.tests.utils import chpwd
from datalad.tests.utils import with_tempfile, assert_in, with_testrepos
from datalad.tests.utils import assert_raises

from nose.tools import eq_, ok_


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_add_sibling(origin, repo_path):

    sshurl = "ssh://push-remote.example.com"
    httpurl1 = "http://remote1.example.com/location"
    httpurl2 = "http://remote2.example.com/location"

    # insufficient arguments
    # we need a dataset to work at
    with chpwd(repo_path):  # not yet there
        assert_raises(InsufficientArgumentsError,
                      add_sibling, url=httpurl1)

    # prepare src
    source = install(repo_path, source=origin, recursive=True)
    # pollute config
    depvar = 'remote.test-remote.datalad-publish-depends'
    source.config.add(depvar, 'stupid', where='local')

    # cannot configure unknown remotes as dependencies
    assert_raises(
        ValueError,
        add_sibling,
        dataset=source,
        name="test-remote",
        url=httpurl1,
        publish_depends=['r1', 'r2'],
        force=True)
    # prior config was changed by failed call above
    eq_(source.config.get(depvar, None), 'stupid')

    res = add_sibling(dataset=source, name="test-remote",
                      url=httpurl1,
                      force=True)

    eq_(res, [basename(source.path)])
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))

    # doing it again doesn't do anything
    res = add_sibling(dataset=source, name="test-remote",
                      url=httpurl1)
    eq_(res, [])
    assert_in("test-remote", source.repo.get_remotes())
    eq_(httpurl1,
        source.repo.get_remote_url("test-remote"))

    # add to another remote automagically taking it from the url
    # and being in the dataset directory
    with chpwd(source.path):
        res = add_sibling(httpurl2)
    eq_(res, [basename(source.path)])
    assert_in("remote2.example.com", source.repo.get_remotes())

    # fail with conflicting url:
    with assert_raises(RuntimeError) as cm:
        add_sibling(dataset=source, name="test-remote",
                    url=httpurl1 + "/elsewhere")
    assert_in("""'test-remote' already exists with conflicting settings""",
              str(cm.exception))

    # don't fail with conflicting url, when using force:
    res = add_sibling(dataset=source, name="test-remote",
                      url=httpurl1 + "/elsewhere", force=True)
    eq_(res, [basename(source.path)])
    eq_(httpurl1 + "/elsewhere",
        source.repo.get_remote_url("test-remote"))

    # add a push url without force fails, since in a way the fetch url is the
    # configured push url, too, in that case:
    with assert_raises(RuntimeError) as cm:
        add_sibling(dataset=source, name="test-remote",
                    url=httpurl1 + "/elsewhere",
                    pushurl=sshurl, force=False)
    assert_in("""'test-remote' already exists with conflicting settings""",
              str(cm.exception))

    # add push url (force):
    res = add_sibling(dataset=source, name="test-remote",
                      url=httpurl1 + "/elsewhere",
                      pushurl=sshurl, force=True)
    eq_(res, [basename(source.path)])
    eq_(httpurl1 + "/elsewhere",
        source.repo.get_remote_url("test-remote"))
    eq_(sshurl,
        source.repo.get_remote_url("test-remote", push=True))

    # recursively:
    res = add_sibling(dataset=source, name="test-remote",
                      url=httpurl1 + "/%NAME",
                      pushurl=sshurl + "/%NAME",
                      recursive=True,
                      force=True)

    eq_(set(res), {basename(source.path),
                   opj(basename(source.path), "subm 1"),
                   opj(basename(source.path), "subm 2")})
    for repo in [source.repo,
                 GitRepo(opj(source.path, "subm 1")),
                 GitRepo(opj(source.path, "subm 2"))]:
        assert_in("test-remote", repo.get_remotes())
        url = repo.get_remote_url("test-remote")
        pushurl = repo.get_remote_url("test-remote", push=True)
        ok_(url.startswith(httpurl1 + '/' + basename(source.path)))
        ok_(url.endswith(basename(repo.path)))
        ok_(pushurl.startswith(sshurl + '/' + basename(source.path)))
        ok_(pushurl.endswith(basename(repo.path)))

    # recursively without template:
    res = add_sibling(dataset=source, name="test-remote-2",
                      url=httpurl1,
                      pushurl=sshurl,
                      recursive=True,
                      force=True)
    eq_(set(res), {basename(source.path),
                   opj(basename(source.path), "subm 1"),
                   opj(basename(source.path), "subm 2")})

    for repo in [source.repo,
                 GitRepo(opj(source.path, "subm 1")),
                 GitRepo(opj(source.path, "subm 2"))]:
        assert_in("test-remote-2", repo.get_remotes())
        url = repo.get_remote_url("test-remote-2")
        pushurl = repo.get_remote_url("test-remote-2", push=True)
        ok_(url.startswith(httpurl1))
        ok_(pushurl.startswith(sshurl))
        if repo != source.repo:
            ok_(url.endswith('/' + basename(repo.path)))
            ok_(pushurl.endswith(basename(repo.path)))
