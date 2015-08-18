# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from abc import ABCMeta, abstractmethod
from os.path import dirname, join as pathjoin, exists, pardir, realpath

from ..support.annexrepo import AnnexRepo
from ..cmd import Runner
from ..utils import get_local_file_url
from ..utils import swallow_outputs
from ..version import __version__

class TestRepo(object):

    __metaclass__ = ABCMeta

    def __init__(self, path, puke_if_exists=True):
        if puke_if_exists and exists(path):
            raise RuntimeError("Directory %s for test repo already exist" % path)
        self.repo = AnnexRepo(path)
        self.runner = Runner(cwd=self.repo.path)
        self.create()

    @property
    def path(self):
        return self.repo.path

    def create_file(self, name, content, annex=False):
        filename = pathjoin(self.path, name)
        with open(filename, 'wb') as f:
            f.write(content.encode())
        (self.repo.annex_add if annex else self.repo.git_add)(name)

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

    @abstractmethod
    def create(self):
        raise NotImplementedError("Should be implemented in ")


class BasicTestRepo(TestRepo):
    """Creates a basic test repository"""
    def create(self):
        self.create_info_file()
        self.create_file('test.dat', '123', annex=False)
        with swallow_outputs() as cmo: # we don't need those outputs at this point
            self.repo.git_commit("Adding a basic INFO file and rudimentary load file for annex testing")
            self.repo.annex_addurl_to_file(
                "test-annex.dat",
                get_local_file_url(realpath(pathjoin(self.path, 'test.dat'))))
            self.repo.git_commit("Adding a rudimentary git-annex load file")
            self.repo.annex_drop("test-annex.dat") # since available from URL
