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
from os.path import dirname, join as pathjoin, exists, pardir, realpath

from ..support.gitrepo import GitRepo
from ..support.annexrepo import AnnexRepo
from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo
from ..cmd import Runner
from ..utils import get_local_file_url
from ..utils import swallow_outputs
from ..utils import swallow_logs

from ..version import __version__
from . import _TEMP_PATHS_GENERATED

# TODO: Probably move automatic "git commit" vs. "git annex proxy -- git commit"
# to AnnexRepo instead of HandleRepo and make use of it herein.


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
        filename = pathjoin(self.path, name)
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
        fileurl = get_local_file_url(realpath(pathjoin(self.path, 'test.dat'))) \
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


class BasicHandleTestRepo(BasicAnnexTestRepo):
    """Creates a basic test handle repository.

    Technically this is just an annex with additional content in a ".datalad"
    subdirectory.
    """

    REPO_CLASS = HandleRepo
    # Everything necessary to distinguish from BasicAnnexTestRepo currently is
    # done by the constructor of HandleRepo class.


class MetadataPTHandleTestRepo(BasicHandleTestRepo):
    """Creates a test handle repository, which provides metadata
    in plaintext format.
    """

    REPO_CLASS = HandleRepo

    def populate(self):
        super(MetadataPTHandleTestRepo, self).populate()
        self.create_file('README',
                         'This is a handle description\nwith multiple lines.\n',
                         annex=False)
        self.create_file('LICENSE',
                         'A license, allowing for several things to do with\n'
                         'the content, provided by this handle.',
                         annex=False)
        self.create_file('AUTHORS',
                         'Benjamin Poldrack <benjaminpoldrack@gmail.com>\n'
                         '# This is a comment\n'
                         '\n'
                         '<justanemail@address.tl>\n'
                         'someone else\n'
                         'digital native <https://www.myfancypage.com/digital>\n',
                         annex=False)
        self.repo._commit("Metadata files created.")


class BasicCollectionTestRepo(BasicGitTestRepo):
    """Creates an empty collection repository"""

    REPO_CLASS = CollectionRepo


class CollectionTestRepo(BasicCollectionTestRepo):
    """Creates a collection repository with two handles."""

    REPO_CLASS = CollectionRepo

    def populate(self):
        super(CollectionTestRepo, self).populate()
        basic_handle = BasicHandleTestRepo()
        basic_handle.create()
        md_handle = MetadataPTHandleTestRepo()
        md_handle.create()
        self.repo.add_handle(basic_handle.repo, "BasicHandle")
        self.repo.add_handle(md_handle.repo, "MetadataHandle")
