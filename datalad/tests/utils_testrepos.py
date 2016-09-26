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
from os.path import dirname, join as opj, exists, pardir
from os import makedirs

from ..config import ConfigManager
from ..support.gitrepo import GitRepo
from ..support.annexrepo import AnnexRepo
from ..cmd import Runner
from ..support.network import get_local_file_url
from ..support.external_versions import external_versions
from ..utils import swallow_outputs
from ..utils import swallow_logs
from ..utils import rmtree
from ..utils import _path_

from ..version import __version__
from . import _TEMP_PATHS_GENERATED

import logging
lgr = logging.getLogger('datalad.tests.testrepos')


class TestRepo(object):

    __metaclass__ = ABCMeta
    __version__ = '0.1'  # Version of test repos -- to be adjusted if anything changes

    VERSION_FILE = '.git/datalad/__version__'
    REPO_CLASS = None  # Assign to the class to be used in the subclass

    def __init__(self, path=None, puke_if_exists=True, cached=True):
        create = True
        self._populated = False
        if not path:
            if not cached:
                from .utils import get_tempfile_kwargs
                path = tempfile.mktemp(**get_tempfile_kwargs({}, prefix='testrepo'))
                # to be removed upon teardown
                _TEMP_PATHS_GENERATED.append(path)
                if exists(path):
                    raise RuntimeError("Directory %s for test repo already exist" % path)
            else:
                path = opj(ConfigManager.dirs.user_cache_dir, 'testrepo-%s' % self.__class__.__name__)
                # check existence and verify version
                if exists(path):
                    # could be part of INFO.txt but I was lazy to fix it up

                    version_file = _path_(path, self.VERSION_FILE)
                    create = "Creating new"
                    if exists(version_file):
                        with open(version_file) as f:
                            version = f.read()
                        if version != self.__version__:
                            create = "Regenerating old (v.%s)" % version
                            rmtree(path)
                        else:
                            create = ""
                            self._populated = True
                        if create:
                            lgr.debug("%s test repository under %s", create, path)

        # swallow logs so we don't print all those about crippled FS etc
        with swallow_logs():
            self.repo = self.REPO_CLASS(path, create=bool(create))

        self.runner = Runner(cwd=path)

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
        if self._populated:
            assert(exists(self.path))
            return  # was already done
        with swallow_outputs():  # we don't need those outputs at this point
            # create version stamp
            version_file = _path_(self.path, self.VERSION_FILE)
            version_file_dir = dirname(version_file)
            if not exists(version_file_dir):
                makedirs(version_file_dir)
            with open(version_file, 'w') as f:
                f.write(self.__version__)
            self.populate()
        self._populated = True

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
        runner = Runner()
        annex_version = external_versions['cmd:annex']
        git_version = external_versions['cmd:git']
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
        self.repo.commit("Adding a basic INFO file and rudimentary "
                             "load file.")

    def create_info_file(self):
        runner = Runner()
        git_version = external_versions['cmd:git']
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
        runner.run(['git', 'submodule', 'add', annex.url, 'subm 1'], **kw)
        runner.run(['git', 'submodule', 'add', annex.url, 'subm 2'], **kw)
        runner.run(['git', 'commit', '-m', 'Added subm 1 and subm 2.'], **kw)
        runner.run(['git', 'submodule', 'update', '--init', '--recursive'], **kw)
        # init annex in subdatasets
        for s in ('subm 1', 'subm 2'):
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
        runner.run(['git', 'submodule', 'add', ds.url, 'sub dataset1'],
                   cwd=self.path, **kw)
        runner.run(['git', 'submodule', 'add', ds.url, 'sub sub dataset1'],
                   cwd=opj(self.path, 'sub dataset1'), **kw)
        runner.run(['git', 'commit', '-m', 'Added sub dataset.'],
                   cwd=opj(self.path, 'sub dataset1'), **kw)
        runner.run(['git', 'commit', '-a', '-m', 'Added subdatasets.'],
                   cwd=self.path, **kw)
        runner.run(['git', 'submodule', 'update', '--init', '--recursive'],
                   cwd=self.path, **kw)
        # init all annexes
        for s in ('', 'sub dataset1', opj('sub dataset1', 'sub sub dataset1')):
            runner.run(['git', 'annex', 'init'],
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
