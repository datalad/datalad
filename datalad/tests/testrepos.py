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

from abc import ABCMeta, abstractmethod, abstractproperty
from six import add_metaclass
from os.path import dirname, join as opj, exists, pardir

from ..support.gitrepo import GitRepo
from ..support.annexrepo import AnnexRepo
from ..cmd import GitRunner
from ..support.network import get_local_file_url
from ..support.external_versions import external_versions
from ..utils import swallow_outputs
from ..utils import swallow_logs
from ..utils import optional_args
from ..utils import better_wraps
from ..version import __version__
from . import _TEMP_PATHS_GENERATED
from .utils import get_tempfile_kwargs
from datalad.customremotes.base import init_datalad_remote


# decorator replacing "with_testrepos":
# - delivers instances of TestRepo* classes instead of paths
# - call assertions (TestRepo*.assert_intact())
#   before and optionally afterwards
# - create new one every time, so we can have defined dirty states?
#   => combine with the option above: If the test is not supposed to change
#   anything, assert_unchanged is triggered and it is okay to use an existing
#   instance
# - no 'network' flavor, but just 'serve_path_via_http' instead?

# - a location for annexed "remote" content
# (see remote_file_fd, remote_file_path)


# new TestRepo* classes:
# - always a "tmp" location or configurable via "datalad.tests.<something>"?
# - assert_unchanged() method
# - properties to
# - (annex) init optional? don't think so (well, might be useful for testing). But: Should be possible to have an
#   uninitialized submodule and a corresponding property




#################### OLD: #########################################

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
###################################################################






@add_metaclass(ABCMeta)
class Item(object):

    def __init__(self, path):  # runner?
        """
        """
        self._path = path

    @property
    def path(self):
        return self._path

    ######### Probably no create() here! Instead we need to override create() of TestRepo* #################
    @abstractmethod
    def create(self):
        pass


class ItemRepo(Item):  # submodule /not a submodule? Define in here?

    def __init__(self, path, url=None, annex=True, branches=None):  # URL to clone from? Create another one inside in-place
        # + submodules?
        pass

    def is_annex(self):  # ??? => Subclasses?
        pass

    def is_git(self):
        pass

    def annex_version(self): #???
        pass

    def is_direct_mode(self): #???
        pass

    def commits(self):  #???
        pass

    def branches(self): #???    # problem: same as mOdified files: how to create?
        pass

    def remotes(self):
        pass

    def create(self):

        ###########
        # with swallow_logs():
        #     self.repo = self.REPO_CLASS(path)
        #     # For additional testing of our datalad remote to not interfere
        #     # and manage to handle all http urls and requests:
        #     if self.REPO_CLASS is AnnexRepo and \
        #             os.environ.get('DATALAD_TESTS_DATALADREMOTE'):
        #         init_datalad_remote(self.repo, 'datalad', autoenable=True)
        ###############

        pass


class ItemFile(Item):  # How about remote files to addurl'd? Dedicated class or parameter?

    def __init__(self, path, content, state, locked, annexed): #runner!

        # option: instead of abs path
        pass

    def is_untracked(self):
        pass

    def is_staged(self):
        pass

    def is_modified(self):   # problem! how?
        pass

    def annex_key(self):
        pass

    def content(self):
        pass

    def is_unlocked(self):
        pass

    def create(self):
        pass


# Is that the solution?
# Insert arbitrary shell commands in the list at any point and let TestRepo.create() just loop over that list

class ItemCommand(Item):

    def __init__(self, cwd, cmd, runner):  #runner? => optional (for protocols, but remember that cwd needs to take precedence
        pass

    def create(self):  #? or __call__?
        pass


class ItemModifyFile(ItemCommand):

    # + optional commit

    def __init__(self, cwd, cmd, runner, file): # file: ItemFile # runner: NOPE! from file
        pass


class ItemNewBranch(ItemCommand):
    # create a new branch (git checkout -b)

    def __init__(self, cwd, cmd, runner, repo): # file: ItemRepo # runner: NOPE from repo
        pass


class ItemCommitFile(ItemCommand):  #file(s)
    # if needed after modification or sth
    pass


class ItemStageFile(ItemCommand):  #file(s)
    # if file(s) need to be staged after they were created

    # + optional commit
    pass


class ItemAddSubmodule(ItemCommand):

    # + optional commit
    pass


@add_metaclass(ABCMeta)
class TestRepo_NEW(object):  # object <=> ItemRepo?
    """
    """

    # version of that test repository; might be used to determine a needed
    # update if used persistently
    version = '0.1'  # TODO: version for abstract class? May be none at all

    # properties accessible by tests in order to base their assertions on it:

    # keys(annex)
    # commit SHA(s)?
    # branches

    # the following might be combined in a single data structure:
    # - files/files in git/files in annex
    # - submodules/hierarchy? dict with files/repos and their properties?
    # - status (what's untracked/staged/locked/unlocked/etc.')

    # Should there be remote location available to install/clone from?
    # => needs to be optional, since cloning would loose untracked/staged things
    #    as well as other branches. So it's possibly not reasonable for some of
    #    the test repos

    # list of commands to execute in order to create this test repository
    _item_definitions = []
    # list of tuples: Item's class and kwargs for constructor
    # example:
    # _item_list = [(ItemRepo, {'path': 'somewhere', 'annex': False, ...})
    #           (ItemFile, {'path': os.path.join('somewhere', 'beneath'),
    #                       'content': 'some content for the file',
    #                       'untracked': True})
    #          ]

    def __init__(self, path=None, runner=None):

        #check path!  => look up, how it is done now in case of persistent ones

        self._runner = runner or GitRunner(cwd=path)

        self.repo = None  # do we want a *Repo instance at all? Don't think so.
                          # we need to serve paths instead
                          # But: It could point to the ItemRepo, which thereby doesn't need to be the top-level one!
                          # => needs special definition
                          # TODO: That means, that the properties need to respect that!

        # TODO: paths relative to TestRepo's path!

        # TODO: for items to be passed the path should be accepted, too!
        #       => additional entry in the tuple, so we can link the instance
        #          here; Needs to be done here due to the path modification!
        #          (see above)
        self._items = {}
        for item in self._item_definitions:
            # pass the Runner if there's None:
            if item[1].get('runner', None) is None:
                item[1]['runner'] = self._runner

            # instantiate and use 'path' as key for the dict of item instances:
            self._items[item[1]['path']] = item[0](**item[1])

        self.create()

    @property
    def path(self):
        return self.repo.path  # TODO

    @property
    def url(self):
        return get_local_file_url(self.path)

    # ???
    @property
    def submodules(self):  # "recursion-limit"?
        return [x for x in self._items if isinstance(x, ItemRepo)]  # and not "self"! and not unregistered

    @abstractmethod
    def assert_intact(self):
        pass

    def create(self):
        # default implementation:  # wouldn't work ATM if Items were passed into others
        # TODO: Could work, if we point to the path of the item in the definition

        # => dict
        for item in self._items:
            item.create()


@optional_args
def with_testrepos_new(t, read_only=False, selector='all'):
    # selector: regex again?
    # based on class names or name/keyword strings?

    # TODO: if possible provide a signature that's (temporarily) compatible with
    # old one to ease RF'ing

    @better_wraps(t)
    def new_func(*arg, **kw):
        pass


#
#  Actual test repositories:
#

class BasicGit(TestRepo_NEW):
    _items = [{'bla': 'palaver'}]
    pass


# 4 times: untracked, modified, staged, all of them
class BasicGitDirty(BasicGit):
    pass


class BasicAnnex(TestRepo_NEW):
    pass


# see above (staged: annex, git, both)
class BasicAnnexDirty(BasicAnnex):
    pass


# ....
class BasicMixed(TestRepo_NEW):
    pass


