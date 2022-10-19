# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
import tempfile
from abc import (
    ABCMeta,
    abstractmethod,
)
from os.path import (
    exists,
)
from os.path import join as opj

from datalad import cfg as dl_cfg
from datalad.customremotes.base import init_datalad_remote

from .. import __version__
from ..support.annexrepo import AnnexRepo
from ..support.external_versions import external_versions
from ..support.gitrepo import GitRepo
from ..support.network import get_local_file_url
from ..utils import (
    swallow_logs,
    swallow_outputs,
)
from . import _TEMP_PATHS_GENERATED
from .utils_pytest import get_tempfile_kwargs

# eventually become a URL to a local file served via http
# that can be used for http/url-based testing
remote_file_url = None


class TestRepo(object, metaclass=ABCMeta):

    REPO_CLASS = None  # Assign to the class to be used in the subclass

    def __init__(self, path=None, puke_if_exists=True):
        if not path:
            path = \
                tempfile.mktemp(**get_tempfile_kwargs(
                    {'dir': dl_cfg.get("datalad.tests.temp.dir")},
                    prefix='testrepo'))
            # to be removed upon teardown
            _TEMP_PATHS_GENERATED.append(path)
        if puke_if_exists and exists(path):
            raise RuntimeError("Directory %s for test repo already exist" % path)
        # swallow logs so we don't print all those about crippled FS etc
        with swallow_logs():
            self.repo = self.REPO_CLASS(path)
            # For additional testing of our datalad remote to not interfere
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
        return get_local_file_url(self.path, compatibility='git')

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
        global remote_file_url
        if not remote_file_url:
            # we need a local file, that is server via a URL
            from datalad.conftest import test_http_server
            remote_file_name = 'testrepo-annex.dat'
            with open(opj(test_http_server.path, remote_file_name), "w") as f:
                f.write("content to be annex-addurl'd")
            remote_file_url = '{}/{}'.format(test_http_server.url, remote_file_name)
        self.create_info_file()
        self.create_file('test.dat', '123\n', annex=False)
        self.repo.commit("Adding a basic INFO file and rudimentary load file for annex testing")
        self.repo.add_url_to_file("test-annex.dat", remote_file_url)
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
        kw = dict(expect_stderr=True)
        self.repo.call_git(
            ['submodule', 'add', annex.url, 'subm 1'], **kw)
        self.repo.call_git(
            ['submodule', 'add', annex.url, '2'], **kw)
        self.repo.commit('Added subm 1 and 2.')
        self.repo.call_git(
            ['submodule', 'update', '--init', '--recursive'], **kw)
        # init annex in subdatasets
        for s in ('subm 1', '2'):
            AnnexRepo(opj(self.path, s), init=True)


class NestedDataset(BasicAnnexTestRepo):

    def populate(self):
        super(NestedDataset, self).populate()
        ds = SubmoduleDataset()
        ds.create()
        kw = dict(expect_stderr=True)
        self.repo.call_git(
            ['submodule', 'add', ds.url, 'sub dataset1'], **kw)
        self.repo.call_git(
            ['-C', opj(self.path, 'sub dataset1'),
             'submodule', 'add', ds.url, 'sub sub dataset1'],
            **kw)
        GitRepo(opj(self.path, 'sub dataset1')).commit('Added sub dataset.')
        self.repo.commit('Added subdatasets.', options=["-a"])
        self.repo.call_git(
            ['submodule', 'update', '--init', '--recursive'],
            **kw)
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
        return get_local_file_url(self.path, compatibility='git')

    def create(self):
        self._ds.create()
