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
import re
from os.path import join as opj, abspath, basename, exists
from os.path import relpath

from git.exc import GitCommandError

from ..dataset import Dataset
from datalad.api import publish, install, create_publication_target_sshwebserver
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
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import ok_exists
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import assert_set_equal

from datalad.utils import on_windows
from datalad.utils import _path_


def _test_correct_publish(target_path, rootds=False, flat=True):

    paths = [_path_(".git/hooks/post-update")]     # hooks enabled in all datasets
    not_paths = [_path_(".git/datalad/metadata")]  # metadata only on publish

    # web-interface html pushed to dataset root
    web_paths = ['index.html', _path_(".git/datalad/web")]
    if rootds:
        paths += web_paths
    # and not to subdatasets
    elif not flat:
        not_paths += web_paths

    for path in paths:
        ok_exists(opj(target_path, path))

    for path in not_paths:
        assert_false(exists(opj(target_path, path)))

    # correct ls_json command in hook content (path wrapped in quotes)
    ok_file_has_content(_path_(target_path, '.git/hooks/post-update'),
                        '.*datalad ls -r --json file \'%s\'.*' % target_path,
                        re_=True,
                        flags=re.DOTALL)


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
        cpkwargs = dict(
            dataset=source,
            target="local_target",
            sshurl="ssh://localhost",
            target_dir=target_path,
            target_url=target_path,
            target_pushurl="ssh://localhost" +
                           target_path,
        )
        create_publication_target_sshwebserver(existing='replace', **cpkwargs)
        eq_(target_path,
            source.repo.get_remote_url("local_target"))
        eq_("ssh://localhost" + target_path,
            source.repo.get_remote_url("local_target", push=True))

        _test_correct_publish(target_path)

        # now, push should work:
        publish(dataset=source, to="local_target")

        # and we should be able to reconfigure
        orig_digests, orig_mtimes = get_mtimes_and_digests(target_path)
        import time; time.sleep(0.1)  # just so that mtimes change
        create_publication_target_sshwebserver(existing='reconfigure', **cpkwargs)
        digests, mtimes = get_mtimes_and_digests(target_path)

        assert_dict_equal(orig_digests, digests)  # nothing should change in terms of content

        # but some files should have been modified
        modified_files = {k for k in mtimes if orig_mtimes.get(k, 0) != mtimes.get(k, 0)}
        # collect which files were expected to be modified without incurring any changes
        ok_modified_files = {_path_('.git/config'), _path_('.git/hooks/post-update'), 'index.html'}
        ok_modified_files.update({f for f in digests if f.startswith(_path_('.git/datalad/web'))})
        assert_set_equal(modified_files, ok_modified_files)


def get_mtimes_and_digests(target_path):
    """Return digests (md5) and mtimes for all the files under target_path"""
    from datalad.utils import find_files
    from datalad.support.digests import Digester
    digester = Digester(['md5'])

    # bother only with existing ones for this test, i.e. skip annexed files without content
    target_files = [
        f for f in find_files('.*', topdir=target_path, exclude_vcs=False, exclude_datalad=False)
        if exists(f)
    ]
    # let's leave only relative paths for easier analysis
    target_files_ = [relpath(f, target_path) for f in target_files]

    digests = {frel: digester(f) for f, frel in zip(target_files, target_files_)}
    mtimes = {frel: os.stat(f).st_mtime for f, frel in zip(target_files, target_files_)}
    return digests, mtimes


@skip_ssh
@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile
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

    for flat in False, True:
        target_path_ = target_dir_tpl = target_path + "-" + str(flat)

        if flat:
            target_dir_tpl += "/%NAME"
            sep = '-'
        else:
            sep = os.path.sep
        remote_name = 'remote-' + str(flat)
        create_publication_target_sshwebserver(target=remote_name,
                                               dataset=source,
                                               sshurl="ssh://localhost" + target_path_,
                                               target_dir=target_dir_tpl,
                                               recursive=True)

        # raise if git repos were not created
        for suffix in [sep + 'subm 1', sep + 'subm 2', '']:
            target_dir = opj(target_path_, basename(src_path) if flat else "").rstrip(os.path.sep) + suffix
            # raise if git repos were not created
            GitRepo(target_dir, create=False)

            _test_correct_publish(target_dir, rootds=not suffix, flat=flat)

        for repo in [source.repo, sub1.repo, sub2.repo]:
            assert_not_in("local_target", repo.get_remotes())

        if flat:
            raise SkipTest('TODO: Make publish work for flat datasets, it currently breaks')
        # now, push should work:
        publish(dataset=source, to=remote_name)
