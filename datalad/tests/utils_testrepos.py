# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
import tempfile

from abc import ABCMeta, abstractmethod
from six import add_metaclass
from os.path import dirname, join as opj, exists, pardir

from ..support.gitrepo import GitRepo
from ..support.annexrepo import AnnexRepo
from ..cmd import Runner
from ..support.network import get_local_file_url
from ..support.external_versions import external_versions
from ..utils import swallow_outputs
from ..utils import swallow_logs

from ..version import __version__
from . import _TEMP_PATHS_GENERATED
from .utils import get_tempfile_kwargs
from datalad.customremotes.base import init_datalad_remote


# we need a local file, that is supposed to be treated as a remote file via
# file-scheme URL
remote_file_fd, remote_file_path = \
    tempfile.mkstemp(**get_tempfile_kwargs({}, prefix='testrepo'))
# to be removed upon teardown
_TEMP_PATHS_GENERATED.append(remote_file_path)
with open(remote_file_path, "w") as f:
    f.write("content to be annex-addurl'd")
# OS-level descriptor needs to be closed!
os.close(remote_file_fd)


@add_metaclass(ABCMeta)
class TestRepo(object):

    REPO_CLASS = None  # Assign to the class to be used in the subclass

    def __init__(self, path=None, puke_if_exists=True):
        if not path:
            path = tempfile.mktemp(**get_tempfile_kwargs({}, prefix='testrepo'))
            # to be removed upon teardown
            _TEMP_PATHS_GENERATED.append(path)
        if puke_if_exists and exists(path):
            raise RuntimeError("Directory %s for test repo already exist" % path)
        # swallow logs so we don't print all those about crippled FS etc
        with swallow_logs():
            self.repo = self.REPO_CLASS(path)
            # For additional testing of our datalad remote to not interfer
            # and manage to handle all http urls and requests:
            if self.REPO_CLASS is AnnexRepo and \
                    os.environ.get('DATALAD_TESTS_DATALADREMOTE'):
                init_datalad_remote(self.repo, 'datalad', autoenable=True)

        self._created = False

    @property
    def path(self):
        return self.repo.path

    @property
    def url(self):
        return get_local_file_url(self.path)

    def create_file(self, name, content, add=True, annex=False):
        filename = opj(self.path, name)
        with open(filename, 'wb') as f:
            f.write(content.encode())
        if add:
            if annex:
                if isinstance(self.repo, AnnexRepo):
                    self.repo.add(name)
                else:
                    raise ValueError("Can't annex add to a non-annex repo.")
            else:
                self.repo.add(name, git=True)

    def create(self):
        if self._created:
            assert(exists(self.path))
            return  # was already done
        with swallow_outputs():  # we don't need those outputs at this point
            self.populate()
        self._created = True

    @abstractmethod
    def populate(self):
        raise NotImplementedError("Should be implemented in sub-classes")


class BasicAnnexTestRepo(TestRepo):
    """Creates a basic test git-annex repository"""

    REPO_CLASS = AnnexRepo

    def populate(self):
        self.create_info_file()
        self.create_file('test.dat', '123\n', annex=False)
        self.repo.commit("Adding a basic INFO file and rudimentary load file for annex testing")
        # even this doesn't work on bloody Windows
        from .utils import on_windows
        fileurl = get_local_file_url(remote_file_path)
        # Note:
        # The line above used to be conditional:
        # if not on_windows \
        # else "https://raw.githubusercontent.com/datalad/testrepo--basic--r1/master/test.dat"
        # This self-reference-ish construction (pointing to 'test.dat'
        # and therefore have the same content in git and annex) is outdated and
        # causes trouble especially in annex V6 repos.
        self.repo.add_url_to_file("test-annex.dat", fileurl)
        self.repo.commit("Adding a rudimentary git-annex load file")
        self.repo.drop("test-annex.dat")  # since available from URL

    def create_info_file(self):
        annex_version = external_versions['cmd:annex']
        git_version = external_versions['cmd:git']
        self.create_file('INFO.txt',
                         "Testrepo: %s\n"
                         "git: %s\n"
                         "annex: %s\n"
                         "datalad: %s\n"
                         % (self.__class__, git_version, annex_version, __version__),
                         annex=False)


class BasicGitTestRepo(TestRepo):
    """Creates a basic test git repository."""

    REPO_CLASS = GitRepo

    def populate(self):
        self.create_info_file()
        self.create_file('test.dat', '123\n', annex=False)
        self.repo.commit("Adding a basic INFO file and rudimentary "
                             "load file.")

    def create_info_file(self):
        git_version = external_versions['cmd:git']
        self.create_file('INFO.txt',
                         "Testrepo: %s\n"
                         "git: %s\n"
                         "datalad: %s\n"
                         % (self.__class__, git_version, __version__),
                         annex=False)


class SubmoduleDataset(BasicAnnexTestRepo):

    def populate(self):

        super(SubmoduleDataset, self).populate()
        # add submodules
        annex = BasicAnnexTestRepo()
        annex.create()
        kw = dict(cwd=self.path, expect_stderr=True)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'add', annex.url, 'subm 1'], **kw)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'add', annex.url, '2'], **kw)
        self.repo.commit('Added subm 1 and 2.')
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'update', '--init', '--recursive'], **kw)
        # init annex in subdatasets
        for s in ('subm 1', '2'):
            AnnexRepo(opj(self.path, s), init=True)


class NestedDataset(BasicAnnexTestRepo):

    def populate(self):
        super(NestedDataset, self).populate()
        ds = SubmoduleDataset()
        ds.create()
        kw = dict(expect_stderr=True)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'add', ds.url, 'sub dataset1'],
            cwd=self.path, **kw)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'add', ds.url, 'sub sub dataset1'],
            cwd=opj(self.path, 'sub dataset1'), **kw)
        GitRepo(opj(self.path, 'sub dataset1')).commit('Added sub dataset.')
        self.repo.commit('Added subdatasets.', options=["-a"])
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'update', '--init', '--recursive'],
            cwd=self.path, **kw)
        # init all annexes
        for s in ('', 'sub dataset1', opj('sub dataset1', 'sub sub dataset1')):
            AnnexRepo(opj(self.path, s), init=True)


class InnerSubmodule(object):

    def __init__(self):
        self._ds = NestedDataset()

    @property
    def path(self):
        return opj(self._ds.path, 'sub dataset1', 'subm 1')

    @property
    def url(self):
        return get_local_file_url(self.path)

    def create(self):
        self._ds.create()
