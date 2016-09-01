# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target ssh web server action

"""

import os
from os.path import join as opj, abspath, basename, exists

from git.exc import GitCommandError

from ..dataset import Dataset
from datalad.api import publish, install, create_publication_target_sshwebserver
from datalad.distribution.install import get_containing_subdataset
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_is_instance
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_not_in
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import skip_ssh
from datalad.utils import on_windows


@skip_ssh
@with_testrepos('.*basic.*', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_target_ssh_simple(origin, src_path, target_rootpath):

    # prepare src
    source = install(path=src_path, source=origin)

    target_path = opj(target_rootpath, "basic")
    create_publication_target_sshwebserver(dataset=source,
                                           target="local_target",
                                           sshurl="ssh://localhost",
                                           target_dir=target_path)

    GitRepo(target_path, create=False)  # raises if not a git repo
    assert_in("local_target", source.repo.get_remotes())
    eq_("ssh://localhost", source.repo.get_remote_url("local_target"))
    # should NOT be able to push now, since url isn't correct:
    assert_raises(GitCommandError, publish, dataset=source, to="local_target")

    # Both must be annex or git repositories
    src_is_annex = AnnexRepo.is_valid_repo(src_path)
    eq_(src_is_annex, AnnexRepo.is_valid_repo(target_path))
    # And target one should be known to have a known UUID within the source if annex
    if src_is_annex:
        annex = AnnexRepo(src_path)
        local_target_cfg = annex.repo.remotes["local_target"].config_reader.get
        eq_(local_target_cfg('annex-ignore'), 'false')
        # hm, but ATM wouldn't get a uuid since url is wrong
        assert_raises(Exception, local_target_cfg, 'annex-uuid')

    # do it again without force:
    with assert_raises(RuntimeError) as cm:
        create_publication_target_sshwebserver(dataset=source,
                                               target="local_target",
                                               sshurl="ssh://localhost",
                                               target_dir=target_path)
    eq_("Target directory %s already exists." % target_path,
        str(cm.exception))

    # now, with force and correct url, which is also used to determine
    # target_dir
    # Note: on windows absolute path is not url conform. But this way it's easy
    # to test, that ssh path is correctly used.
    if not on_windows:
        # add random file under target_path, to explicitly test existing=replace
        open(opj(target_path, 'random'), 'w').write('123')

        create_publication_target_sshwebserver(dataset=source,
                                               target="local_target",
                                               sshurl="ssh://localhost" +
                                                      target_path,
                                               existing='replace')
        eq_("ssh://localhost" + target_path,
            source.repo.get_remote_url("local_target"))
        eq_("ssh://localhost" + target_path,
            source.repo.get_remote_url("local_target", push=True))

        # ensure target tree actually replaced by source
        assert_false(exists(opj(target_path, 'random')))

        if src_is_annex:
            annex = AnnexRepo(src_path)
            local_target_cfg = annex.repo.remotes["local_target"].config_reader.get
            eq_(local_target_cfg('annex-ignore'), 'false')
            eq_(local_target_cfg('annex-uuid').count('-'), 4)  # valid uuid

        # again, by explicitly passing urls. Since we are on localhost, the
        # local path should work:
        create_publication_target_sshwebserver(dataset=source,
                                               target="local_target",
                                               sshurl="ssh://localhost",
                                               target_dir=target_path,
                                               target_url=target_path,
                                               target_pushurl="ssh://localhost" +
                                                              target_path,
                                               existing='replace')
        eq_(target_path,
            source.repo.get_remote_url("local_target"))
        eq_("ssh://localhost" + target_path,
            source.repo.get_remote_url("local_target", push=True))

        # pushed web-interface html to dataset
        assert(exists(opj(target_path, "index.html")))
        # pushed web-interface assets directory to dataset
        assert(exists(opj(target_path, ".git", "datalad", "web")))
        # enabled dataset post-update hook
        assert(exists(opj(target_path, ".git", "hooks", "post-update")))
        # not created dataset metatadata directory in dataset
        assert_false(exists(opj(target_path, ".git", "datalad", "metadata")))
        # correct ls_json command in hook content
        assert_in('datalad ls -r --json file %s' % target_path[:-1],
                  open(opj(target_path, ".git", "hooks", "post-update")).read())

        # now, push should work:
        publish(dataset=source, to="local_target")


@skip_ssh
@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_target_ssh_recursive(origin, src_path, target_path):
    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_subdatasets(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True,
                  create=False).checkout("master")

    sub1 = Dataset(opj(src_path, "subm 1"))
    sub2 = Dataset(opj(src_path, "subm 2"))

    create_publication_target_sshwebserver(dataset=source,
                                           sshurl="ssh://localhost",
                                           target_dir=target_path + "/%NAME",
                                           recursive=True)

    # raise if git repos were not created
    for suffix in ['-subm 1', '-subm 2', '']:
        target_dir = opj(target_path, basename(src_path) + suffix)
        # raise if git repos were not created
        GitRepo(target_dir, create=False)

    # web-interface html pushed to dataset
    assert(exists(opj(target_dir, "index.html")))
    # enabled dataset post-update hook
    assert(exists(opj(target_dir, ".git", "hooks", "post-update")))
    # hook content has the correct ls_json command
    assert_in('datalad ls -r --json file %s' % target_dir[:-1],
              open(opj(target_dir, ".git", "hooks", "post-update")).read())

    for repo in [source.repo, sub1.repo, sub2.repo]:
        assert_not_in("local_target", repo.get_remotes())
