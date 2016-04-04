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
from os.path import join as opj, abspath, basename
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
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module, skip_if, skip_if_on_windows
from datalad.tests.utils import ok_clean_git


@skip_if(cond=not os.environ.get('DATALAD_TESTS_SSH'),
         msg="Run this test by setting the DATALAD_TESTS_SSH")
@skip_if_on_windows
@with_testrepos('.*basic.*', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_target_ssh_simple(origin, src_path, target_path):

    # prepare src
    source = install(path=src_path, source=origin)

    create_publication_target_sshwebserver(dataset=source,
                                           target="local_target",
                                           sshurl="ssh://localhost",
                                           target_dir=opj(target_path, "basic"))

    GitRepo(opj(target_path, "basic"), create=False) # raises if not a git repo
    assert_in("local_target", source.repo.git_get_remotes())
    eq_("ssh://localhost" + opj(target_path, "basic"),
        source.repo.git_get_remote_url("local_target"))
    # should be able to push now:
    publish(dataset=source, dest="local_target")


@skip_if(cond=not os.environ.get('DATALAD_TESTS_SSH'),
         msg="Run this test by setting the DATALAD_TESTS_SSH")
@skip_if_on_windows
@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_target_ssh_recursive(origin, src_path, target_path):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True,
                  create=False).git_checkout("master")

    sub1 = Dataset(opj(src_path, "sub1"))
    sub2 = Dataset(opj(src_path, "sub2"))

    create_publication_target_sshwebserver(dataset=source,
                                           target="local_target",
                                           sshurl="ssh://localhost",
                                           target_dir=target_path + "/%NAME",
                                           recursive=True)

    # raise if git repos were not created:
    t_super = GitRepo(opj(target_path, basename(src_path)), create=False)
    t_sub1 = GitRepo(opj(target_path, basename(src_path) + "-sub1"),
                     create=False)
    t_sub2 = GitRepo(opj(target_path, basename(src_path) + "-sub2"),
                     create=False)

    for repo in [source.repo, sub1.repo, sub2.repo]:
        assert_in("local_target", repo.git_get_remotes(),
                  "missing remote in {0}".format(repo.path))

    eq_("ssh://localhost" + t_super.path,
        source.repo.git_get_remote_url("local_target"))
    eq_("ssh://localhost" + t_sub1.path,
        sub1.repo.git_get_remote_url("local_target"))
    eq_("ssh://localhost" + t_sub2.path,
        sub2.repo.git_get_remote_url("local_target"))

    # target can be used for publishing:

    publish(dataset=source, dest="local_target", recursive=True)