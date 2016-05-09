# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import tempfile

from abc import ABCMeta, abstractmethod
from os.path import dirname, join as opj, exists, pardir, realpath

from ..support.gitrepo import GitRepo
from ..support.annexrepo import AnnexRepo
from ..cmd import Runner
from ..utils import get_local_file_url
from ..utils import swallow_outputs
from ..utils import swallow_logs

from ..version import __version__
from . import _TEMP_PATHS_GENERATED


class TestRepo(object):

    __metaclass__ = ABCMeta

    REPO_CLASS = None # Assign to the class to be used in the subclass

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
        self.runner = Runner(cwd=self.repo.path)
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
            (self.repo.annex_add if annex else self.repo.git_add)(name)

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
        self.repo.git_commit("Adding a basic INFO file and rudimentary load file for annex testing")
        # even this doesn't work on bloody Windows
        from .utils import on_windows
        fileurl = get_local_file_url(realpath(opj(self.path, 'test.dat'))) \
                  if not on_windows \
                  else "https://raw.githubusercontent.com/datalad/testrepo--basic--r1/master/test.dat"
        self.repo.annex_addurl_to_file("test-annex.dat", fileurl)
        self.repo.git_commit("Adding a rudimentary git-annex load file")
        self.repo.annex_drop("test-annex.dat")  # since available from URL

    def create_info_file(self):
        runner = Runner()
        annex_version = runner.run("git annex version")[0].split()[2]
        git_version = runner.run("git --version")[0].split()[2]
        self.create_file('INFO.txt',
                         "git: %s\n"
                         "annex: %s\n"
                         "datalad: %s\n"
                         % (git_version, annex_version, __version__),
                         annex=False)


class BasicGitTestRepo(TestRepo):
    """Creates a basic test git repository."""

    REPO_CLASS = GitRepo

    def populate(self):
        self.create_info_file()
        self.create_file('test.dat', '123\n', annex=False)
        self.repo.git_commit("Adding a basic INFO file and rudimentary "
                             "load file.")

    def create_info_file(self):
        runner = Runner()
        git_version = runner.run("git --version")[0].split()[2]
        self.create_file('INFO.txt',
                         "git: %s\n"
                         "datalad: %s\n"
                         % (git_version, __version__),
                         annex=False)


class SubmoduleDataset(BasicAnnexTestRepo):

    def populate(self):

        super(SubmoduleDataset, self).populate()
        # add submodules
        annex = BasicAnnexTestRepo()
        annex.create()
        from datalad.cmd import Runner
        runner = Runner()
        kw = dict(cwd=self.path, expect_stderr=True)
        runner.run(['git', 'submodule', 'add', annex.url, 'sub1'], **kw)
        runner.run(['git', 'submodule', 'add', annex.url, 'sub2'], **kw)
        runner.run(['git', 'commit', '-m', 'Added sub1 and sub2.'], **kw)
        runner.run(['git', 'submodule', 'update', '--init', '--recursive'], **kw)
        # init annex in subdatasets
        for s in ('sub1', 'sub2'):
            runner.run(['git', 'annex', 'init'],
                       cwd=opj(self.path, s), expect_stderr=True)


class NestedDataset(BasicAnnexTestRepo):

    def populate(self):
        super(NestedDataset, self).populate()
        ds = SubmoduleDataset()
        ds.create()
        from datalad.cmd import Runner
        runner = Runner()
        kw = dict(expect_stderr=True)
        runner.run(['git', 'submodule', 'add', ds.url, 'subdataset'],
                   cwd=self.path, **kw)
        runner.run(['git', 'submodule', 'add', ds.url, 'subsubdataset'],
                   cwd=opj(self.path, 'subdataset'), **kw)
        runner.run(['git', 'commit', '-m', 'Added subdataset.'],
                   cwd=opj(self.path, 'subdataset'), **kw)
        runner.run(['git', 'commit', '-a', '-m', 'Added subdatasets.'],
                   cwd=self.path, **kw)
        runner.run(['git', 'submodule', 'update', '--init', '--recursive'],
                   cwd=self.path, **kw)
        # init all annexes
        for s in ('', 'subdataset', opj('subdataset', 'subsubdataset')):
            runner.run(['git', 'annex', 'init'],
                       cwd=opj(self.path, s), expect_stderr=True)


class InnerSubmodule(object):

    def __init__(self):
        self._ds = NestedDataset()

    @property
    def path(self):
        return opj(self._ds.path, 'subdataset', 'sub1')

    @property
    def url(self):
        return get_local_file_url(self.path)

    def create(self):
        self._ds.create()
