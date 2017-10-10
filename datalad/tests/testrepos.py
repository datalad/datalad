# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

"""datalad's test repository mechanism
"""

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
from ..support.exceptions import CommandError
from ..utils import auto_repr
from ..utils import optional_args
from ..utils import better_wraps
from ..version import __version__
from . import _TEMP_PATHS_GENERATED
from .utils import get_tempfile_kwargs
from ..dochelpers import exc_str, borrowdoc
from datalad.customremotes.base import init_datalad_remote
from datalad import cfg

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


class InvalidTestRepoDefinitionError(Exception):
    """Thrown if the definition of a test repository is invalid
    """

    def __init__(self, msg=None, repo=None, item=None, index=None):
        """

        Parameters
        ----------
        msg: str
            Additional Message. A default message will be generated from the
            other parameters to the extend they are provided. Then `msg` is
            appended as an additional information on the specific kind of error.
        repo: class
            The subclass of `TestRepo` the error was occurring in.
        item: class
            The class of the item causing the error.
        index: int
            Index of the definition list the error causing item is defined at.
        """
        super(self.__class__, self).__init__(msg)
        self.repo = repo
        self.item = item
        self.index = index

    def __str__(self):
        to_str = "{}: Invalid definition".format(self.__class__)
        to_str += " in {}".format(self.repo) if self.repo else ""
        to_str += " at index {}".format(self.index) if self.index else ""
        to_str += " for item {}.".format(self.item) if self.item else "."
        to_str += os.linesep
        return to_str + (self.message if self.message else "")


class TestRepoCreationError(Exception):
    """Thrown if the creation of a test repository failed
    """

    def __init__(self, msg, repo=None, item=None):
        """

        Parameters
        ----------
        msg: str
            Additional Message. A default message will be generated from the
            other parameters to the extend they are provided. Then `msg` is
            appended as an additional information on the specific kind of error.
        repo: class
            The subclass of `TestRepo` the error was occurring in.
        item: class
            The class of the item causing the error.
        """
        super(self.__class__, self).__init__(msg)
        self.repo = repo
        self.item = item

    def __str__(self):
        to_str = "{}: Creation failed".format(self.__class__)
        to_str += " in {}".format(self.repo) if self.repo else ""
        to_str += " for item {}.".format(self.item) if self.item else "."
        to_str += os.linesep
        return to_str + (self.message if self.message else "")


@auto_repr
@add_metaclass(ABCMeta)
class Item(object):
    """Base class for test repository definition items
    """

    def __init__(self, path, runner=None):  # runner?
        """

        Parameters
        ----------
        path: str
            absolute path the item is associated with. Note, that in test repo
            definitions all paths have to be relative to the test repo's
            root. Conversion is done within `TestRepo_NEW.__init__()`
        runner: Runner or None
            `Runner` instance to use for creation of the item. By default an
            instance is created using basename(path) as CWD.
        """
        self._path = path
        self._runner = runner or GitRunner(cwd=os.path.basename(path))

    @property
    def path(self):
        """ absolute path the item is associated with
        """
        return self._path

    @property
    def local_url(self):
        """ same as `path` but as a file-scheme URL

        Something like: file:///that/is/where/my/item/lives
        """
        return get_local_file_url(self._path)
    # TODO: use serve_path_via_http in an additional property?

    @abstractmethod
    def create(self):
        """Let the actual thing defined by this item come to life

        Needs to be implemented by subclasses.
        """
        pass


@auto_repr
class ItemRepo(Item):
    """Defines a (sub-) repository for test repositories

    It can either be a plain git or an annex.
    Note, that this might be part of a hierarchy, but defines just one
    repository.
    Also note, that not all of its properties can be specified during
    instantiation. Things like adding a submodule, creating a new branch and so
    on, are done by instances of `ItemCommand`, which take other items as
    parameters and should modify their properties accordingly.
    """

    def __init__(self, path, src=None, runner=None,
                 annex=True, annex_version=None, annex_direct=None,
                 annex_init=True):
        """

        Parameters
        ----------
        path: str
            absolute path where to create this repository. Note, that in test
            repo definitions all paths have to be relative to the test repo's
            root. Conversion is done within `TestRepo_NEW.__init__()`
        src: str or None
            path or URL to clone the repository from
        runner: Runner or None
            `Runner` instance to use for creation of the item. By default an
            instance is created using basename(path) as CWD.
        annex: bool
            whether or not this repository should be an annex
        annex_version: int or None
            annex repository version to use. If None, it's up to git-annex
            (or `datalad.tests.repo.version` config) to decide
        annex_direct: bool or None
            whether annex should use direct mode. If None, it's up to git-annex
            (or `datalad.tests.repo.direct` config) to decide
        """
        # TODO: What to do if annex settings are contradicting whatever is
        # enforced by git-annex or our test config?
        # Should we just go for it, adjust properties and leave it to the
        # TestRepo (sub-)class to raise or accept such a situation?
        # Pro: It depends on the purpose of the entire setup whether or not it
        # still makes sense. For example: Having a direct mode submodule within
        # an otherwise non direct mode hierarchy wouldn't be possible if direct
        # mode is enforced and it's pointless if the entire beast is in direct
        # mode.
        # Or just raise? (Would be from within self.create(), since we need to
        # see what annex actually does.)

        if not annex and (annex_version or annex_direct or annex_init):
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="Parameters 'annex_version' or 'annex_direct' or "
                    "'annex_init' were specified, while 'annex' wasn't True."
            )
        if annex and annex_version and annex_direct and annex_version >= 6:
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="There is no direct mode, if you use annex repository "
                    "version 6 or greater."
            )
        if not annex_init and (annex_version or annex_direct):
            # Note, that this is about test repos! They are used within the
            # tests by actual datalad code. That code cannot respect what is
            # specified herein regarding the possible initialization of that
            # repo.
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="Parameters 'annex_version' or 'annex_direct' were "
                    "specified, while 'annex_init' wasn't True."
            )

        super(self.__class__, self).__init__(path=path, runner=runner)
        self._src = src
        self._annex = annex
        self._annex_version = annex_version
        self._annex_direct = annex_direct
        self._annex_init = annex_init

    # TODO: May be let properties return anything only after creation?
    @property
    def is_annex(self):
        """Whether or not the repository is an annex

        Returns
        -------
        bool
        """
        return self._annex

    @property
    def is_git(self):
        """Whether or not the repository is a PLAIN git

        Opposite of `self.is_annex`. Just for convenience.

        Returns
        -------
        bool
        """
        return not self._annex

    @property
    def annex_version(self):
        """Annex repository version

        Returns
        -------
        int
        """
        return self._annex_version

    @property
    def is_direct_mode(self):
        """Whether or not the annex is in direct mode

        Returns
        -------
        bool
        """
        return self._annex_direct

    @property
    def annex_is_initialized(self):
        """Whether or not `git-annex init` was called after creation

        Returns
        -------
        bool
        """
        return self._annex_init

    # TODO: How to represent commits? SHAs, messages are kind of obvious but
    # what about structure?
    # Just a plain list? A list per branch?
    def commits(self):
        pass

    # TODO: How to represent branches? Just the names or names plus commit SHAs?
    def branches(self):
        pass

    # TODO: How to represent remotes? Just the names or names plus url(s)?
    # What about special remotes?
    def remotes(self):
        # Note: names and url(s)
        pass

    def submodules(self):
        pass

    def superproject(self):
        pass

    def create(self):
        """Creates the physical repository
        """

        # TODO: Rethink whether or not it makes sense to explicitly set `cwd`
        # for the Runner calls. Default Runner uses that path anyway ...

        # Note: self.path is the directory we want to create in. But it's also
        # CWD of the default Runner. Therefore we need to make sure the
        # directory exists and is empty:
        if not exists(self._path):
            os.makedirs(self._path)
        elif not os.path.isdir(self._path):
            # not a directory
            raise TestRepoCreationError("Target path {} is not a directory."
                                        "".format(self._path),
                                        item=self.__class__)
        if os.listdir(self._path):
            # not empty
            raise TestRepoCreationError("Target path {} is not empty."
                                        "".format(self._path),
                                        item=self.__class__)

        # create the git repository:
        create_cmd = ['git']
        create_cmd.extend(['clone', self._src, os.curdir]
                          if self._src else ['init'])
        try:
            self._runner.run(create_cmd, cwd=self._path)
        except CommandError as e:
            # raise TestRepoCreationError instead, so TestRepo can add
            # more information
            raise TestRepoCreationError("Failed to create git repository{}({})"
                                        "".format(os.linesep, exc_str(e)),
                                        item=self.__class__)

        # we want to make it an annex
        if self._annex and self._annex_init:
            annex_cmd = ['git', 'annex', 'init']
            if self._annex_version:
                annex_cmd.append('--version=%s' % self._annex_version)
            try:
                self._runner.run(['git', 'annex', 'init'], cwd=self._path)
            except CommandError as e:
                raise TestRepoCreationError("Failed to initialize annex{}({})"
                                            "".format(os.linesep, exc_str(e)),
                                            item=self.__class__)

            # TODO: This is code from old test repos that still uses actual
            # datalad code (AnnexRepo in particular). Should be replaced.
            # Furthermore "datalad.tests.dataladremote" needs a default to
            # use obtain()
            from datalad.config import anything2bool
            if anything2bool(cfg.get("datalad.tests.dataladremote")):
                # For additional testing of our datalad remote to not interfere
                # and manage to handle all http urls and requests:
                init_datalad_remote(AnnexRepo(self._path, init=False, create=False),
                                    'datalad', autoenable=True)

            if self._annex_direct:
                annex_cmd = ['git', 'annex', 'direct']
                try:
                    self._runner.run(annex_cmd, cwd=self._path)
                except CommandError as e:
                    raise TestRepoCreationError(
                        "Failed to switch to direct mode{}({})"
                        "".format(os.linesep, exc_str(e)),
                        item=self.__class__)

            # TODO: Verify annex_version and annex_direct from .git/config


@auto_repr
class ItemSelf(ItemRepo):
    """ItemRepo to mark the repository a TestRepo is pointing to.

    A TestRepo's definition must contain exactly one ItemSelf. It's used to
    determine the repository within a possible hierarchy the tests are supposed
    to run on. In most cases it's probably just the top-level one, but it could
    point anywhere within the hierarchy, so a test automatically runs on a repo,
    that has a superproject (and submodules).
    """

    @borrowdoc(ItemRepo, '__init__')
    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

# Note:
# States: untracked, modified, staged, new file, typechanged

# TODO:
class ItemFile(Item):  # How about remote files to addurl'd? Dedicated class or parameter?
    """
    """
    # snippets:

            # raise InvalidTestRepoDefinitionError(
            #     item=self.__class__,
            #     msg="Parameters 'annex_version' or 'annex_direct' or "
            #         "'annex_init' were specified, while 'annex' wasn't True."
            # )
            # raise TestRepoCreationError("Target path {} is not empty."
            #                             "".format(self._path),
            #                             item=self.__class__)

    def __init__(self, path, src=None, runner=None,
                 content=None, state=None, locked=True, annexed=False):
        """

        Parameters
        ----------
        path: str
            absolute path where to create this file
        runner: Runner or None
            `Runner` instance to use for creation of the item. By default an
            instance is created using basename(path) as CWD.
        state: tuple of str

            tuple (index, working_tree)
            see man git-status => short format
            TODO

        annexed: bool
            whether or not this file should be annexed
        src: str or None
            path or url to annex-addurl from. Mutually exclusive with `content`.
            Valid only if `annexed` is True.
        content: str
            content of the file. Mutually exclusive with `src`.
            Valid only if `annexed` is True.
        locked: bool
            whether or not the file should be locked.
            Valid only if `annexed` is True.
        """

        super(self.__class__, self).__init__(path=path, runner=runner)
        self._content = content
        self._state = state  # EnsureChoice?
        self._locked = locked  # TODO: consider direct mode. There's no lock ...
        self._annexed = annexed

    @property
    def is_untracked(self):
        return self._state[1] == 'untracked'

    # TODO: state needs to be tuple! (modified + staged)
    # Or flags?
    @property
    def is_staged(self):
        return self._state[0] in ['modified', 'added', 'typechanged', 'deleted', 'renamed']

    @property
    def is_modified(self):   # problem! how?
        return self._state == 'modified'

    @property
    def is_unlocked(self):
        pass

    @property
    def content(self):
        return self._content

    def annex_key(self):
        pass

    def is_unlocked(self):
        pass

    def create(self):
        if exists(self.path):
            raise  # What error?
    def create(self):
        if exists(self.path):
            raise TestRepoCreationError# What error?
        with open(self.path, 'w') as f:
            f.write(self.content)
        # TODO: depends on state: add, annex-add, commit, ...


# TODO:
class ItemInfoFile(ItemFile):

    default_path = 'INFO.txt'  # assigned

    def __init__(self, class_, path=None, annexed=False, content=None, definition=None):
        self._content = content or \
            "git: {git}{ls}" \
            "annex: {annex}{ls}" \
            "datalad: {dl}{ls}" \
            "TestRepo: {repo}({v}){ls}" \
            "Definition:{ls}" \
            "".format(ls=os.linesep,
                      repo=class_,
                      v=class_.version,
                      git=external_versions['cmd:git'],
                      annex=external_versions['cmd:annex'],
                      dl=__version__)
            # TODO: git-annex, definition
        super(self.__class__, self).__init__(path=path, annexed=annexed)  # ....


# TODO: some standard "remote" files; classes like ItemInfoFile?
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


# Is that the solution?
# Insert arbitrary shell commands in the list at any point and let TestRepo.create() just loop over that list

class ItemCommand(Item):

    def __init__(self, cwd, cmd, runner):  #runner? => optional (for protocols, but remember that cwd needs to take precedence
        super(self.__class__, self).__init__(path=cwd, runner=runner)

    def create(self):  #? or __call__?
        pass


class ItemModifyFile(ItemCommand):

    # + optional commit

    def __init__(self, cwd, runner, item): # item: ItemFile # runner: NOPE! from file
        super(self.__class__, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


class ItemNewBranch(ItemCommand):
    # create a new branch (git checkout -b)

    def __init__(self, cwd, runner, item): # item: ItemRepo # runner: NOPE from repo
        super(self.__class__, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


class ItemCommitFile(ItemCommand):  #file(s)
    # if needed after modification or sth

    def __init__(self, cwd, runner):
        super(self.__class__, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


class ItemStageFile(ItemCommand):  #file(s)
    # if file(s) need to be staged after they were created

    # + optional commit
    def __init__(self, cwd, runner):
        super(self.__class__, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


class ItemAddSubmodule(ItemCommand):

    # + optional commit
    def __init__(self, cwd, runner):
        super(self.__class__, self).__init__(cwd=cwd, cmd=cmd, runner=runner)

# TODO: Commands for (special remotes)!


@auto_repr
@add_metaclass(ABCMeta)
class TestRepo_NEW(object):  # object <=> ItemRepo?
    """Base class for test repositories
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
    # Note:
    # - item references are paths
    # - 'path' and 'cwd' arguments are relative to TestRepo's root
    # - toplevel repo: path = None ???

    # example:
    # _item_list = [(ItemRepo, {'path': 'somewhere', 'annex': False, ...})
    #           (ItemFile, {'path': os.path.join('somewhere', 'beneath'),
    #                       'content': 'some content for the file',
    #                       'untracked': True})
    #          ]

    def __init__(self, path=None, runner=None):

        self._path = path
        # TODO
        # check path!  => look up, how it is done now in case of persistent ones
        # Note: If we want to test whether an existing one is valid, we need to
        # do it after instantiation of items.
        # But: Probably just fail. Persistent ones are to be kept in some kind
        # of registry and delivered by with_testrepos without trying to
        # instantiate again.

        self._runner = runner or GitRunner(cwd=path)
        self.repo = None
        self._items = {}
        self._execution = []

        for item, index in zip(self._item_definitions,
                               range(len(self._item_definitions))):

            # 1. necessary adaptions of arguments for instantiation
            # pass the Runner if there's None:
            if item[1].get('runner', None) is None:
                item[1]['runner'] = self._runner

            # 'path' and 'cwd' arguments in definitions are relative to the
            # TestRepo's root, but absolute in the Item instances. Replace them
            # for instantiation, but keep `r_path` for identification
            # (key in the items dict):
            if issubclass(item[0], ItemCommand):
                # paths are relative in definitions
                try:
                    r_cwd = item[1]['cwd']
                except KeyError:
                    # 'cwd' is mandatory for ItemCommand:
                    raise InvalidTestRepoDefinitionError(
                        msg="Missing argument 'cwd' for {cl}:{ls}"
                            "{cl}({args})".format(ls=os.linesep,
                                                  cl=item[0].__class__,
                                                  args=item[1]),
                        repo=self.__class__,
                        item=item[0].__class__,
                        index=index
                        )
                # store absolute path for instantiation
                item[1]['cwd'] = opj(self._path, r_cwd)

                # 'item' arguments in ItemCommand definitions are paths, since
                # we can't reference an actual object therein.
                # Do the conversion:
                ref_item = item[1].get('item')
                if ref_item:
                    try:
                        item[1]['item'] = self._items[ref_item]
                    except KeyError:
                        raise InvalidTestRepoDefinitionError(
                            "Item {it} referenced before it was "
                            "defined:{ls}{cl}({args})"
                            "".format(ls=os.linesep,
                                      it=ref_item,
                                      cl=item[0].__class__,
                                      args=item[1]),
                            repo=self.__class__,
                            item=item[0].__class__,
                            index=index
                        )

            if issubclass(item[0], ItemRepo) or issubclass(item[0], ItemFile):
                # paths are relative in definitions
                # Additionally 'path' is mandatory for ItemRepo and ItemFile.
                # Exception: ItemInfoFile has a default path
                r_path = item[1].get('path', None)
                if not r_path:
                    if issubclass(item[0], ItemInfoFile):
                        r_path = ItemInfoFile.default_path
                    else:
                        raise InvalidTestRepoDefinitionError(
                            msg="Missing argument 'path' for {cl}:{ls}"
                                "{cl}({args})".format(ls=os.linesep,
                                                      cl=item[0].__class__,
                                                      args=item[1]),
                            repo=self.__class__,
                            item=item[0].__class__,
                            index=index
                            )
                # `r_path` identifies an item; it must be unique:
                if r_path in self._items:
                    raise InvalidTestRepoDefinitionError(
                        msg="Ambiguous definition. 'path' argument for ItemRepo"
                            " and ItemFile instances must be unique. "
                            "Encountered second use of {p}:{ls}{cl}({args})"
                            "".format(ls=os.linesep,
                                      p=r_path,
                                      cl=item[0].__class__,
                                      args=item[1]),
                            repo=self.__class__,
                            item=item[0].__class__,
                            index=index
                        )

                # store absolute path for instantiation
                item[1]['path'] = opj(self._path, r_path)

            # END path conversion
            # For ItemRepo and ItemFile the relative path is kept in `r_path`

            # special case ItemInfoFile
            if issubclass(item[0], ItemInfoFile):
                # pass item definitions to the info file:
                item[1]['definition'] = self._item_definitions

            # 2. instantiate items
            # Note, that there are two stores of instances: self._items and
            # self._execution. ItemCommands are used for creation only and are
            # stored in self._execution only (which then is to be used by
            # self.create()).
            # Other items, namely ItemRepo and ItemFile objects are additionally
            # stored in self._items for later access by properties of
            # TestRepo_NEW and its subclasses.

            try:
                item_instance = item[0](**item[1])
            except InvalidTestRepoDefinitionError as e:
                # add information the Item classes can't know:
                e.repo = self.__class__
                e.index = index
                raise e

            self._execution.append(item_instance)
            if not issubclass(item[0], ItemCommand):
                self._items[r_path] = item_instance

            # 3. special case: save reference to "self":
            if item[0].__class__ is ItemSelf:
                if self.repo:
                    # we had one already
                    raise InvalidTestRepoDefinitionError(
                            "{cl} must not be defined multiple times. "
                            "Found a second definition:{ls}{cl}({args})"
                            "".format(ls=os.linesep,
                                      cl=ItemSelf,
                                      args=item[1]),
                            repo=self.__class__,
                            item=ItemSelf,
                            index=index
                    )
                self.repo = self._items[r_path]

        # - not sure yet whether we want to instantly and unconditionally create
        # - do we need some TestRepoCreationError? (see path checking)
        self.create()

    @property
    def path(self):
        return self.repo.path

    @property
    def url(self):
        # TODO: Again: Just file-scheme or use sth like serve_via_http in addition?
        return get_local_file_url(self.path)

    # TODO
    @property
    def submodules(self):  # "recursion-limit"?
        # just a draft: (invalid)
        return [x for x in self._items if isinstance(x, ItemRepo)]
        # and not "self"! and not unregistered
        # and beneath self ...

    @abstractmethod
    def assert_intact(self):
        """Assertions to run to check integrity of this test repository

        Needs to be implemented by subclasses.
        """
        pass

    def create(self):
        """Physically create the beast
        """
        # default implementation:
        for item in self._execution:
            item.create()


@optional_args
def with_testrepos_new(t, read_only=False, selector='all'):
    # selector: regex again?
    # based on class names or name/keyword strings?

    # TODO: if possible provide a signature that's (temporarily) compatible with
    # old one to ease RF'ing

    # TODO: if assert_intact fails and readonly == True, re-create for other tests

    @better_wraps(t)
    def new_func(*arg, **kw):
        pass


#
#  Actual test repositories:
#

class BasicGit(TestRepo_NEW):
    _item_definitions = [(ItemSelf, {'path': '.',
                                     'annex': False}),
                         (ItemFile, {'path': 'test.dat',
                                     'content': "123",
                                     'annexed': False,
                                     'state': 'staged'}),  # or just untracked and include staging in committing?
                         (ItemInfoFile, {}),
                         (ItemCommitFile, {'cwd': '.',
                                           'items': ['test.dat', 'INFO.txt']})  # TODO: It's a list! see TestRepo_NEW.__init__!
                         ]

    def __init__(self):
        super(BasicGit).__init__()
        pass

    def assert_intact(self):
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

# v6 adjusted branch ...

# Datasets (.datalad/config, .datalad/metadata ...) ?