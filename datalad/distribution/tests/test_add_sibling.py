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
    # insufficient arguments
    # we need a dataset to work at
    with chpwd(repo_path):  # not yet there
        assert_raises(InsufficientArgumentsError,
                      add_sibling, url="http://some.remo.te/location")

    # prepare src
    source = install(repo_path, source=origin, recursive=True)[0]
    # pollute config
    depvar = 'remote.test-remote.datalad-publish-depends'
    source.config.add(depvar, 'stupid', where='local')

    # cannot configure unknown remotes as dependencies
    assert_raises(
        ValueError,
        add_sibling,
        dataset=source,
        name="test-remote",
        url="http://some.remo.te/location",
        publish_depends=['r1', 'r2'],
        force=True)
    # prior config was changed by failed call above
    eq_(source.config.get(depvar, None), 'stupid')

    res = add_sibling(dataset=source, name="test-remote",
                      url="http://some.remo.te/location",
                      force=True)

    eq_(res, [basename(source.path)])
    assert_in("test-remote", source.repo.get_remotes())
    eq_("http://some.remo.te/location",
        source.repo.get_remote_url("test-remote"))

    # doing it again doesn't do anything
    res = add_sibling(dataset=source, name="test-remote",
                      url="http://some.remo.te/location")
    eq_(res, [])
    assert_in("test-remote", source.repo.get_remotes())
    eq_("http://some.remo.te/location",
        source.repo.get_remote_url("test-remote"))

    # add to another remote automagically taking it from the url
    # and being in the dataset directory
    with chpwd(source.path):
        res = add_sibling("http://some.remo.te2/location")
    eq_(res, [basename(source.path)])
    assert_in("some.remo.te2", source.repo.get_remotes())

    # fail with conflicting url:
    with assert_raises(RuntimeError) as cm:
        add_sibling(dataset=source, name="test-remote",
                    url="http://some.remo.te/location/elsewhere")
    assert_in("""'test-remote' already exists with conflicting settings""",
              str(cm.exception))

    # don't fail with conflicting url, when using force:
    res = add_sibling(dataset=source, name="test-remote",
                      url="http://some.remo.te/location/elsewhere", force=True)
    eq_(res, [basename(source.path)])
    eq_("http://some.remo.te/location/elsewhere",
        source.repo.get_remote_url("test-remote"))

    # add a push url without force fails, since in a way the fetch url is the
    # configured push url, too, in that case:
    with assert_raises(RuntimeError) as cm:
        add_sibling(dataset=source, name="test-remote",
                    url="http://some.remo.te/location/elsewhere",
                    pushurl="ssh://push.it", force=False)
    assert_in("""'test-remote' already exists with conflicting settings""",
              str(cm.exception))

    # add push url (force):
    res = add_sibling(dataset=source, name="test-remote",
                      url="http://some.remo.te/location/elsewhere",
                      pushurl="ssh://push.it", force=True)
    eq_(res, [basename(source.path)])
    eq_("http://some.remo.te/location/elsewhere",
        source.repo.get_remote_url("test-remote"))
    eq_("ssh://push.it",
        source.repo.get_remote_url("test-remote", push=True))

    # recursively:
    res = add_sibling(dataset=source, name="test-remote",
                      url="http://some.remo.te/location/%NAME",
                      pushurl="ssh://push.it/%NAME", recursive=True,
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
        ok_(url.startswith("http://some.remo.te/location/" + basename(source.path)))
        ok_(url.endswith(basename(repo.path)))
        ok_(pushurl.startswith("ssh://push.it/" + basename(source.path)))
        ok_(pushurl.endswith(basename(repo.path)))

    # recursively without template:
    res = add_sibling(dataset=source, name="test-remote-2",
                      url="http://some.remo.te/location",
                      pushurl="ssh://push.it/",
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
        ok_(url.startswith("http://some.remo.te/location"))
        ok_(pushurl.startswith("ssh://push.it/"))
        if repo != source.repo:
            ok_(url.endswith('/' + basename(repo.path)))
            ok_(pushurl.endswith(basename(repo.path)))
