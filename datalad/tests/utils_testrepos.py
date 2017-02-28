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

from datalad.customremotes.base import init_datalad_remote

@add_metaclass(ABCMeta)
class TestRepo(object):

    REPO_CLASS = None  # Assign to the class to be used in the subclass

    def __init__(self, path=None, puke_if_exists=True):
        if not path:
            from .utils import get_tempfile_kwargs
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
        fileurl = get_local_file_url(opj(self.path, 'test.dat')) \
                  if not on_windows \
                  else "https://raw.githubusercontent.com/datalad/testrepo--basic--r1/master/test.dat"
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
            '', ['git', 'submodule', 'add', annex.url, 'subm 2'], **kw)
        self.repo._git_custom_command(
            '', ['git', 'commit', '-m', 'Added subm 1 and subm 2.'], **kw)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'update', '--init', '--recursive'], **kw)
        # init annex in subdatasets
        for s in ('subm 1', 'subm 2'):
            self.repo._git_custom_command(
                '', ['git', 'annex', 'init'],
                cwd=opj(self.path, s), expect_stderr=True)


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
        self.repo._git_custom_command(
            '', ['git', 'commit', '-m', 'Added sub dataset.'],
            cwd=opj(self.path, 'sub dataset1'), **kw)
        self.repo._git_custom_command(
            '', ['git', 'commit', '-a', '-m', 'Added subdatasets.'],
            cwd=self.path, **kw)
        self.repo._git_custom_command(
            '', ['git', 'submodule', 'update', '--init', '--recursive'],
            cwd=self.path, **kw)
        # init all annexes
        for s in ('', 'sub dataset1', opj('sub dataset1', 'sub sub dataset1')):
            self.repo._git_custom_command(
                '', ['git', 'annex', 'init'],
                cwd=opj(self.path, s), expect_stderr=True)


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
