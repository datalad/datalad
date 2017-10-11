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
from ..dochelpers import exc_str, borrowdoc, single_or_plural
from datalad.customremotes.base import init_datalad_remote
from datalad import cfg
from datalad.utils import assure_list
from six import string_types
import shlex
from datalad.utils import on_windows
from .utils import eq_, assert_is_instance, assert_raises, assert_in

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


# TODO: - Our actual tests could instantiate Items (without creating them!) to
#         represent changes and then just call assert_intact() to test for
#         everything without the need to think of everything when writing the
#         test.
#       - That way, we can have helper functions for such assertions like:
#         take that file from the TestRepo and those changes I specified and
#         test, whether or not those changes and those changes only actually
#         apply. This would just copy the Item from TestRepo, inject the changes
#         and call assert_intact()


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
        to_str = "Invalid definition"
        to_str += " in {}".format(self.repo) if self.repo else ""
        to_str += " at index {}".format(self.index) if self.index else ""
        to_str += " for item {}.".format(self.item) if self.item else "."
        to_str += os.linesep
        return to_str + (self.message if self.message else "")


class TestRepoCreationError(Exception):
    """Thrown if the creation of a test repository failed
    """

    def __init__(self, msg, repo=None, item=None, index=None):
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
        self.index = index

    def __str__(self):
        to_str = "Creation failed"
        to_str += " in {}".format(self.repo) if self.repo else ""
        to_str += " at index {}".format(self.index) if self.index else ""
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
            instance is created using dirname(path) as CWD.
        """
        self._path = path
        self._runner = runner or GitRunner(cwd=os.path.dirname(path))

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

    def assert_intact(self):
        # Note: Went for this solution, since assert_intact isn't required by
        # subclasses of ItemCommand. @abstractmethod would force them to
        # override. This way overriding is "enforced" only, if it's actually
        # called.
        raise InvalidTestRepoDefinitionError(
            msg="{it} didn't override Item.assert_intact()."
                "".format(it=self.__class__),
            item=self.__class__
        )


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
                 annex_init=None):
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
            instance is created using dirname(path) as CWD.
        annex: bool
            whether or not this repository should be an annex
        annex_version: int or None
            annex repository version to use. If None, it's up to git-annex
            (or `datalad.tests.repo.version` config) to decide
        annex_direct: bool or None
            whether annex should use direct mode. If None, it's up to git-annex
            (or `datalad.tests.repo.direct` config) to decide
        annex_init: bool or None
            whether or not to initialize the annex. Valid only if `annex`
            is True. By default it is set to True, if `annex` is True. Set to
            False if you want to clone an annex and not annex-init that clone.
            It doesn't make sense in other cases.
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

        if annex and annex_init is None:
            annex_init = True

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

        super(ItemRepo, self).__init__(path=path, runner=runner)

        # TODO: datalad config!

        self._src = src
        self._annex = annex
        self._annex_version = annex_version if annex else None
        self._annex_direct = annex_direct if annex else False
        self._annex_init = annex_init if annex else False
        self._files = set()  # ... of ItemFile
        self._submodules = set()  # ... of ItemRepo
        self._commits = []
        self._branches = []
        self._remotes = []
        self._super = None

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
    @property
    def commits(self):
        return self._commits

    # TODO: How to represent branches? Just the names or names plus commit SHAs?
    @property
    def branches(self):
        return self._branches

    # TODO: How to represent remotes? Just the names or names plus url(s)?
    # What about special remotes?
    @property
    def remotes(self):
        # Note: names and url(s)
        return self._remotes

    @property
    def submodules(self):
        return self._submodules

    @property
    def superproject(self):
        return self._super

    # TODO: This might change. May be we need a self._items and look for ItemFile in it. Consider untracked files!
    # Also: Let it be Items instead of paths, and return paths only from TestRepo? Would be easier for internal access.
    @property
    def files(self):
        return  self._files
        #return [os.path.relpath(f_.path, self.path) for f_ in self._files]

    def create(self):
        """Creates the physical repository
        """

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
        if self._src:
            # we just cloned
            self.remotes.add('origin')

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

    def assert_intact(self):
        """This supposed to make basic tests on whether or not what is stored in
        this ItemRepo instance actually is, what can be found on disc plus some
        consistency checks for the object itself.
        Everything else is out of scope and needs to be tested by ItemRepo and
        the subclasses of TestRepo.
        """

        # object consistency
        if self.is_git:
            assert(not self.is_annex)
            assert(self.annex_is_initialized is False)
            assert(self.annex_version is None)
            assert(self.is_direct_mode is False)

        if self.is_annex:
            assert(not self.is_git)
            if self.annex_version or self.is_direct_mode:
                assert(self.annex_is_initialized is True)

        if self._src:
            # Note: self._src indicates that we cloned the repo from somewhere.
            # Therefore we have 'origin'. Theoretically there could be an
            # ItemCommand that removed that remote, but left self._src.
            # If that happens, that ItemCommand probably should be adapted to
            # also remove self._src.
            assert(self.remotes)

        [assert_is_instance(b, string_types) for b in self.branches]
        for c in self.commits:
            assert_is_instance(c, tuple)
            eq_(len(c), 2)
            assert_is_instance(c[0], string_types)  # SHA
            assert_is_instance(c[1], string_types)  # message

        if self.branches:
            assert self.commits
            # Not necessarily vice versa? Could be just detached HEAD, I guess.

        [assert_is_instance(f_, ItemFile) for f_ in self._files]
        [assert_is_instance(r_, ItemRepo) for r_ in self._submodules]
        # TODO: What about unregistered repos beneath? May be just part of TestRepo instance, not the ItemRepo.

        for it in self.files:
            assert(it.path.startswith(self.path))
            it.assert_intact()
            # Note: Not actually sure how this would look if there were files
            # moved from one repo to another within the testrepo setup. In case
            # we ever get there: Reconsider whether this should be true:
            [assert_in(commit, self.commits) for commit in it.commits]

        for it in self.submodules:
            assert(it.path.startswith(self.path))
            it.assert_intact()
            # TODO: For now, there is no place to easily check for commits that
            # changed submodules (not commits WITHIN them)
            assert(it.superproject is self)


##################
        # physical appearance:
##################


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
        super(ItemSelf, self).__init__(*args, **kwargs)


@auto_repr
class ItemFile(Item):
    """
    """

    # file status constants corresponding to git-status' short format
    UNTRACKED = '?'
    UNMODIFIED = ' '
    MODIFIED = 'M'
    ADDED = 'A'
    DELETED = 'D'
    RENAMED = 'R'
    COPIED = 'C'
    TYPECHANGED = 'T'  # Note: This one is missing in git-status short format
    UPDATED_BUT_UNMERGED = 'U'

    def __init__(self, path, runner=None,
                 content=None, state=None, commit_msg=None,
                 annexed=False, key=None, src=None, locked=None):
        """

        Parameters
        ----------
        path: str
            absolute path where to create this file
        runner: Runner or None
            `Runner` instance to use for creation of the item. By default an
            instance is created using dirname(path) as CWD.
        content: str
            content of the file. Mutually exclusive with `src`.
        state: tuple of str
            a tuple defining the state of the file in the index and the working
            tree respectively. This is pretty much the way git-status represents
            it in its short format. Constants are available from this class, so
            you can specify `state` using those constants.
            For example, a file that was newly added but not yet committed would
            have the state `(ItemFile.ADDED, ItemFile.UNMODIFIED)`.
            See the short format in git-status' man page if you're not familiar
            with that concept.
        commit_msg: str
            commit message to use, if the file is to be committed. That means
            `state` has to be (ItemFile.UNMODIFIED, ItemFile.UNMODIFIED).
            By default the commit message would read
            "ItemFile: Added file <path> to [git | annex]"
        annexed: bool
            whether or not this file should be annexed
        key: str
            annex' key for that file. Valid only if `annexed` is True. If not
            given it will be determined automatically. While this should usually
            work, please consider that providing information on what SHOULD be
            and compare to what IS the case, is the whole point of testing.
            Relying on what actually happened generally breaks the logic of
            testing to a certain extend.
        src: str or None
            path or url to annex-addurl from. Mutually exclusive with `content`.
            Valid only if `annexed` is True.
        locked: bool or None
            whether or not the file should be locked by annex.
            Valid only if `annexed` is True.
            Note, that locked/unlocked isn't available in annex direct mode.
        """

        # TODO: Use constraints (like EnsureChoice for 'state') for sanity
        # checks on the arguments?

        if src and content:
            raise InvalidTestRepoDefinitionError(
                msg="Parameters 'src' and 'content' were specified for "
                    "{it}({p}) but are mutually exclusive.".format(
                        it=self.__class__,
                        p=path
                    ),
                item=self.__class__
            )

        if not src and not content:
            raise InvalidTestRepoDefinitionError(
                msg="Neither 'src' nor 'content were specified for "
                    "{it}({p}).".format(
                        it=self.__class__,
                        p=path
                    ),
                item=self.__class__
            )

        if commit_msg and state != (ItemFile.UNMODIFIED, ItemFile.UNMODIFIED):
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'commit_msg' was specified for {it}({p}) but "
                    "'state' doesn't suggest to commit the file or is invalid "
                    "for initial definition."
                    "".format(it=self.__class__,
                              p=path),
                item=self.__class__
            )

        if not annexed:
            invalid_parameters = []
            if src:
                invalid_parameters.append('src')
            if locked is not None:  # False is equally invalid!
                invalid_parameters.append('locked')
            if key:
                invalid_parameters.append('key')
            if invalid_parameters:
                raise InvalidTestRepoDefinitionError(
                    msg="{param_s} {params} {was_were} specified for "
                        "{it}({p}) but are invalid when 'annexed' is False"
                        "".format(
                            param_s=single_or_plural("Parameter",
                                                     "Parameters",
                                                     len(invalid_parameters)
                                                     ),
                            params="and ".join(invalid_parameters),
                            was_were=single_or_plural("was",
                                                      "were",
                                                      len(invalid_parameters)
                                                      ),
                            it=self.__class__,
                            p=path
                        ),
                    item=self.__class__
                )

        if src and state != (ItemFile.ADDED, ItemFile.UNMODIFIED):
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'src' was specified, but state doesn't suggest to"
                    "annex-addurl or state is invalid for initial definition:"
                    "{ls}{it}({p}, src={src}, state={state})"
                    "".format(ls=os.linesep,
                              it=self.__class__,
                              p=path,
                              src=src,
                              state=state),
                item=self.__class__
            )

        super(ItemFile, self).__init__(path=path, runner=runner)
        self._content = content
        self._state_index = state[0]
        self._state_worktree = state[1]
        self._commit_msg = commit_msg
        self._src = src
        self._locked = locked  # TODO: consider direct mode. There's no lock ...
        self._annexed = annexed
        self._key = key
        self._commits = []
        self._content_present = None  # to be set when actually adding the file
                                      # to annex

    @property
    def annexed(self):
        return self._annexed

    @property
    def is_untracked(self):
        return self._state_index == ItemFile.UNTRACKED and \
               self._state_worktree == ItemFile.UNTRACKED

    @property
    def is_staged(self):
        return self._state_index in [ItemFile.MODIFIED,
                                     ItemFile.ADDED,
                                     ItemFile.DELETED,
                                     ItemFile.RENAMED,
                                     ItemFile.COPIED,
                                     ItemFile.TYPECHANGED] and \
               self._state_worktree == ItemFile.UNMODIFIED

    @property
    def is_modified(self):
        return self._state_index == ItemFile.MODIFIED or \
               self._state_worktree == ItemFile.MODIFIED

    @property
    def is_clean(self):  # TODO: Better name
        return self._state_index == ItemFile.UNMODIFIED and \
               self._state_worktree == ItemFile.UNMODIFIED

    @property
    def is_unlocked(self):
        return self._locked is False  # not `None`!

    @property
    def is_locked(self):
        return self._locked is True # not `None`!

    @property
    def content_available(self):
        return self._content_present

    @property
    def content(self):
        return self._content

    @property
    def annex_key(self):
        return self._key

    @property
    def commits(self):
        """list of the commits involving this file

        Returns
        -------
        tuple
            (str, str)
            First element is the commit's SHA, the second its message
        """
        return self._commits

    def create(self):
        if exists(self.path):
            raise TestRepoCreationError(
                msg="Path {p} already exists.".format(p=self.path),
                item=self.__class__
            )
        if self.content:
            try:
                with open(self.path, 'w') as f:
                    f.write(self.content)
            except EnvironmentError as e:
                raise TestRepoCreationError(
                    msg="The following exception occurred while trying to write to "
                        "file {p}:{ls}{exc}".format(ls=os.linesep,
                                                    p=self.path,
                                                    exc=exc_str(e)
                                                    ),
                    item=self.__class__
                )

        # Furthermore, we can git-add, git-annex-add and commit the new file.
        # Anything more complex (like add, commit, change the content,
        # stage again, ...) cannot be achieved by create(), since this would
        # require way too complex definitions. That's what ItemCommand(item=...)
        # is for instead.
        # TODO: If we allow to add/commit here, we can't easily notify ItemRepo
        #       about it! This would require TestRepo.__init__ (or .create()) to
        #       inspect the tree. (keep in mind there might be untracked files
        #       or even repos that were not registered as submodules)

        to_add = False
        to_commit = False
        if self.is_untracked:
            # we are done
            return
        elif self._state_index == ItemFile.ADDED and \
                self._state_worktree == ItemFile.UNMODIFIED:
            # we need to add
            to_add = True
        elif self.is_clean:
            # we need to add and commit
            to_add = True
            to_commit = True
        else:
            # everything else is invalid as an item's initial definition
            raise InvalidTestRepoDefinitionError(
                msg="Requested state ('{i_state}', '{w_state}') of {it}({p}) is"
                    " invalid as initial definition. Instead specify "
                    "ItemCommand(s) like ItemModifyFile to further manipulate "
                    "this item."
                    "".format(i_state=self._state_index,
                              w_state=self._state_worktree,
                              it=self.__class__,
                              p=self.path
                              ),
                item=self.__class__
            )

        if to_add:
            # TODO: This part needs attention for V6. See gh-1798
            add_cmd = ['git']
            if self._annexed:
                # git-annex
                add_cmd.append('annex')
                if self._src:
                    # we want to annex-addurl
                    add_cmd.extend(['addurl', self._src, '--file=%s' % self.path])
                else:
                    # we want to annex-add
                    add_cmd.extend(['add', self.path])
            else:
                # git-add
                add_cmd.extend(['add', self.path])

            try:
                # Note, that the default runner comes from TestRepo and has its
                # default cwd set to TestRepo's root. We don't know, whether or
                # not this is right here. We could as well be in a submodule.
                self._runner.run(add_cmd, cwd=os.path.dirname(self.path))
            except CommandError as e:
                # raise TestRepoCreationError instead, so TestRepo can add
                # more information
                raise TestRepoCreationError(
                    msg="Failed to add {it}({p}) ({exc})"
                        "".format(it=self.__class__,
                                  p=self.path,
                                  exc=exc_str(e)
                                  ),
                        item=self.__class__
                )

            if self._annexed:
                # we just annex-added. So the content is available ATM.
                self._content_present = True

            if self._annexed and not self._key:
                # look it up
                lookup_cmd = ['git', 'annex', 'lookupkey', self._path]
                try:
                    out, err = self._runner.run(lookup_cmd,
                                                cwd=os.path.dirname(self.path))
                except CommandError as e:
                    # raise TestRepoCreationError instead, so TestRepo can add
                    # more information
                    raise TestRepoCreationError(
                        msg="Failed to look up key for {it}({p}) ({exc})"
                            "".format(it=self.__class__,
                                      p=self.path,
                                      exc=exc_str(e)
                                      ),
                        item=self.__class__
                    )
                self._key = out.strip()

            # If we just annex-addurl'd we should get the content:
            if self._annexed and self._src:
                with open(self.path, 'r') as f:
                    self._content = f.read()

        if self.is_unlocked:
            # unlock needs to be done before committing (at least in v6 it
            # would be 'typechanged' otherwise)
            # TODO: Double check the result for v5
            # TODO: When and how to check for direct mode? Remember, that direct
            # mode could be enforced without being specified in the definition
            unlock_cmd = ['git', 'annex', 'unlock', self.path]
            try:
                self._runner.run(unlock_cmd, cwd=os.path.dirname(self.path))
            except CommandError as e:
                # raise TestRepoCreationError instead, so TestRepo can add
                # more information
                raise TestRepoCreationError(
                    msg="Failed to unlock {it}({p}) ({exc})"
                        "".format(it=self.__class__,
                                  p=self.path,
                                  exc=exc_str(e)
                                  ),
                    item=self.__class__
                )

        if to_commit:
            if not self._commit_msg:
                self._commit_msg = "{it}: Added file {p} to {git_annex}" \
                                   "".format(it=self.__class__,
                                             p=self.path,
                                             git_annex="annex" if self._annexed
                                             else "git")
            commit_cmd = ['git', 'commit', '-m', '"%s"' % self._commit_msg,
                          '--', self.path]
            try:
                self._runner.run(commit_cmd, cwd=os.path.dirname(self.path))
            except CommandError as e:
                # raise TestRepoCreationError instead, so TestRepo can add
                # more information
                raise TestRepoCreationError(
                    msg="Failed to commit {it}({p}) ({exc})"
                        "".format(it=self.__class__,
                                  p=self.path,
                                  exc=exc_str(e)
                                  ),
                    item=self.__class__
                )

            # get the commit's SHA for property:
            lookup_SHA_cmd = ['git', 'log', '-n', '1',
                              "--pretty=format:\"%H%n%B\""]
            try:
                out, err = self._runner.run(lookup_SHA_cmd,
                                            cwd=os.path.dirname(self.path))
            except CommandError as e:
                # raise TestRepoCreationError instead, so TestRepo can add
                # more information
                raise TestRepoCreationError(
                    msg="Failed to look up commit SHA for {it}({p}) ({exc})"
                        "".format(it=self.__class__,
                                  p=self.path,
                                  exc=exc_str(e)
                                  ),
                    item=self.__class__
                )
            commit_SHA = out.splitlines()[0]
            commit_msg = os.linesep.join(out.splitlines()[1:])
            self._commits.append((commit_SHA, commit_msg))

        return

    def assert_intact(self):
        """This supposed to make basic tests on whether or not what is stored in
        this ItemFile instance actually is, what can be found on disc plus some
        consistency checks for the object itself.
        Everything else is out of scope and needs to be tested by ItemRepo and
        the subclasses of TestRepo.
        """
        # object consistency
        if self.is_untracked:
            assert(self.commits is [])
            assert(self.annexed is False)

        if self.annexed is False:
            assert(self.annex_key is None)
            assert(self.content_available is None)
            assert(not self.is_untracked)

        assert(os.path.isabs(self.path))

        # physical appearance:
        if self.content_available or not self.annexed:
            with open(self.path, 'r') as f:
                content_from_disc = f.read()
            eq_(content_from_disc, self.content)

        if self.is_locked:
            assert_raises(EnvironmentError, open, self.path, 'w')
        # TODO:
        # - commits
        # - annex key
        # - state? This might need annex-proxy and ignore-submodules, but since
        #   we have a certain file to specify it might work


@auto_repr
class ItemInfoFile(ItemFile):

    default_path = 'INFO.txt'  # needs to accessible by TestRepo.__init__

    def __init__(self, class_, definition=None,
                 path=None, runner=None, annexed=False, content=None,
                 # directly committed on creation:
                 state=(ItemFile.UNMODIFIED, ItemFile.UNMODIFIED),
                 commit_msg=None,
                 src=None,
                 locked=None):
        if not content:
            content = "git: {git}{ls}" \
                      "annex: {annex}{ls}" \
                      "datalad: {dl}{ls}" \
                      "TestRepo: {repo}({v}){ls}" \
                      "Definition:{ls}{definition}" \
                      "".format(ls=os.linesep,
                                repo=class_,
                                v=class_.version,
                                git=external_versions['cmd:git'],
                                annex=external_versions['cmd:annex'],
                                dl=__version__,
                                definition=definition  # TODO: pprint or sth ...
                                )
        if not commit_msg and state == (ItemFile.UNMODIFIED,
                                        ItemFile.UNMODIFIED):
            # default commit_msg only if caller didn't change the state
            # otherwise either the state is invalid for initial definition
            # altogether or it's not to be committed and a message passed to
            # superclass will result in InvalidTestRepoDefinitionError
            commit_msg = "{}: Added ItemInfoFile ({})." \
                         "".format(class_, os.path.basename(path))

        super(ItemInfoFile, self).__init__(
            path=path, runner=runner, content=content, state=state,
            commit_msg=commit_msg, annexed=annexed, src=src, locked=locked)


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


# TODO: Commands need to notify the ItemRepos! Otherwise we don't know what belongs where!
#       Same is true for instant file adding/committing
# TODO: runner calls need to set cwd! By default it's the TestRepo's runner, so cwd is its root!

@auto_repr
class ItemCommand(Item):
    """Base class for commands to be included in TestRepo's definition

    Also provides a generic call to an arbitrary command. Use with caution!
    Since it's generic it doesn't know in what way it might manipulate any items
    and therefore can't set their properties accordingly.
    """

    def __init__(self, cmd, runner=None, item=None, cwd=None, repo=None):
        """

        Parameters
        ----------
        runner: Runner or None
        cmd: list
        item: Item or list of Item or None
        cwd: str or None
        repo: ItemRepo or None
        """

        # if `cwd` wasn't specified, use root of `repo`
        if not cwd:
            cwd = repo.path

        super(ItemCommand, self).__init__(path=cwd, runner=runner)

        if isinstance(cmd, string_types):
            self._cmd = shlex.split(cmd, posix=not on_windows)
        elif isinstance(cmd, list):
            self._cmd = cmd
        else:
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'cmd' is expected to be a list or a string."
                    "Found {type}: {cmd}"
                    "".format(type=type(cmd),
                              cmd=cmd
                              ),
                item=ItemCommand
            )

        self._ref_items = assure_list(item)
        self._cwd = cwd
        self._repo = repo

        # if items were passed, append them:
        if self._ref_items:
            self._cmd.append('--')
            self._cmd.extend([it.path for it in self._ref_items])

    def create(self):
        """Default implementation to run `self._cmd`

        May (and probably SHOULD) be overridden by subclasses. While it can be
        used by subclasses to run the actual command, they should at least
        extend it to modify properties of involved Items.
        """

        try:
            self._runner.run(self._cmd, cwd=self._cwd)
        except CommandError as e:
            # raise TestRepoCreationError instead, so TestRepo can add
            # more information
            raise TestRepoCreationError(
                msg="Command failed: {it}({cmd}) ({exc})"
                    "".format(it=self.__class__,
                              cmd=self._cmd,
                              exc=exc_str(e)
                              ),
                item=self.__class__
            )


@auto_repr
class ItemCommit(ItemCommand):
    """Item to include an explicit call to git-commit in TestRepo's definition

    This is needed in particular when you want to commit several Items at once,
    which can't be done via their definitions, since they don't know each other
    or the ItemRepo they belong to.
    """

    def __init__(self, runner, item=None, cwd=None, msg=None, repo=None):

        if not repo:
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is required. By default this could "
                    "also be derived from 'cwd' by the TestRepo (sub-)class, "
                    "but apparently this didn't happen."
                    "".format(it=self.__class__),
                item=self.__class__
            )

        item = assure_list(item)
        # build default commit message:
        if not msg:
            if item:
                msg = "{self}: Committed {what}: {items}".format(
                        self=ItemCommit,
                        what=single_or_plural("item", "items",
                                              len(item),
                                              include_count=True),
                        items=", ".join(["{it}({p})"
                                         "".format(it=it,
                                                   p=it.path)
                                         for it in item])
                )
            else:
                msg = "{self}: Committed staged changes." \
                            "".format(self=ItemCommit)

        # build command call:
        commit_cmd = ['git', '--work-tree=.', 'commit',
                      '-m', '"%s"' % msg]
        # Note, that items will be appended by super class

        super(ItemCommit, self).__init__(runner=runner, item=item, cwd=cwd,
                                         cmd=commit_cmd, repo=repo)

    def create(self):
        # run the command:
        super(ItemCommit, self).create()

        # now, get the commit let the items know:
        # Note, that git-log should work in direct mode without --work-tree
        lookup_sha_cmd = ['git', 'log', '-n', '1',
                          "--pretty=format:%H%n%B"]
        try:
            out, err = self._runner.run(lookup_sha_cmd, cwd=self._cwd)
        except CommandError as e:
            # raise TestRepoCreationError instead, so TestRepo can add
            # more information
            raise TestRepoCreationError(
                msg="Failed to look up commit SHA for {it}({p}) ({exc})"
                    "".format(it=self.__class__,
                              p=self.path,
                              exc=exc_str(e)
                              ),
                item=self.__class__
            )
        commit_sha = out.splitlines()[0]
        commit_msg = out[len(commit_sha):].strip().strip('\"')

        # notify involved items:
        self._repo._commits.append((commit_sha, commit_msg))
        for it in self._ref_items:
            it._commits.append((commit_sha, commit_msg))
            it._state_index = ItemFile.UNMODIFIED
            # TODO: Does "git commit -- myfile" stage that file before?
            # If so: adjust it._state_worktree as well!

            # If ItemRepo didn't know about the committed items, it definitely
            # should now!
            # TODO: Not sure yet, how to add those (may be just _items):
            if isinstance(it, ItemFile):
                self._repo._files.add(it)
            elif isinstance(it, ItemRepo):
                self._repo._submodules.add(it)


@auto_repr
class ItemDropFile(ItemCommand):
    """Item to include an explicit call to git-annex-drop in TestRepo's
    definition
    """

    def __init__(self, runner, item=None, cwd=None, repo=None):

        if not repo:
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is required. By default this could "
                    "also be derived from 'cwd' by the TestRepo (sub-)class, "
                    "but apparently this didn't happen."
                    "".format(it=self.__class__),
                item=self.__class__
            )
        if not (isinstance(repo, ItemRepo) and repo.is_annex):
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is not an ItemRepo or not an annex:"
                    " {repo}({p}).".format(it=self.__class__,
                                           repo=str(repo)),
                item=self.__class__
            )

        item = assure_list(item)

        # build command call:
        drop_cmd = ['git', 'annex', 'drop']

        super(ItemDropFile, self).__init__(cmd=drop_cmd, runner=runner,
                                           item=item, cwd=cwd, repo=repo)

    def create(self):
        # run the command:
        super(ItemDropFile, self).create()

        # notify files:
        for it in self._ref_items:
            it._content_present = False


@auto_repr
class ItemModifyFile(ItemCommand):

    # + optional commit

    def __init__(self, cwd, runner, item): # item: ItemFile # runner: NOPE! from file
        super(ItemModifyFile, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


@auto_repr
class ItemNewBranch(ItemCommand):
    # create a new branch (git checkout -b)

    def __init__(self, cwd, runner, item): # item: ItemRepo # runner: NOPE from repo
        super(ItemNewBranch, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


@auto_repr
class ItemAddFile(ItemCommand):  #file(s)
    # if file(s) need to be staged after they were created

    # + optional commit
    def __init__(self, cwd, runner):
        super(ItemAddFile, self).__init__(cwd=cwd, cmd=cmd, runner=runner)


@auto_repr
class ItemAddSubmodule(ItemCommand):

    # + optional commit
    def __init__(self, cwd, runner):
        super(ItemAddSubmodule, self).__init__(cwd=cwd, cmd=cmd, runner=runner)

# TODO: Commands for (special) remotes


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

        # TODO: Probably the same mechanism has to be applied for
        # ItemFile(src=...) in order to be able to assign predefined
        # ItemFile instances!
        def _path2item(def_item, def_idx, kw):
            """internal helper to convert item references in definitions

            Items need to be referenced by path in TestRepo definitions.
            Converts those paths and assigns the actual objects instead.

            Parameters
            ----------
            def_item: tuple
                an entry of _item_definition
            def_idx: int
                index of that entry
            kw: str
                the keyword to convert
            """

            ref_it = def_item[1].get(kw)
            if ref_it:
                # might be a list, therefore always treat as such
                ref_it = assure_list(ref_it)
                def_item[1][kw] = []
                for r in ref_it:
                    try:
                        def_item[1][kw].append(self._items[r])
                    except KeyError:
                        raise InvalidTestRepoDefinitionError(
                            "Item {it} referenced before definition:"
                            "{ls}{cl}({args})"
                            "".format(ls=os.linesep,
                                      it=r,
                                      cl=def_item[0].__name__,
                                      args=def_item[1]),
                            repo=self.__class__,
                            item=def_item[0].__name__,
                            index=def_idx
                        )

                # if it's not a list undo assure_list:
                if len(def_item[1][kw]) == 1:
                    def_item[1][kw] = def_item[1][kw][0]

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

            if not (issubclass(item[0], Item) and isinstance(item[1], dict)):
                raise InvalidTestRepoDefinitionError(
                    msg="Malformed definition entry. An entry of a TestRepo's "
                        "definition list is expected to be a tuple, consisting "
                        "of a subclass of Item and a dict, containing kwargs "
                        "for its instantiation. Entry at index {idx} is "
                        "violating this constraint:{ls}{cl}({args})"
                        "".format(ls=os.linesep,
                                  cl=item[0],
                                  args=item[1]
                                  ),
                    repo=self.__class__,
                    item=item[0].__name__,
                    index=index
                )

            # 1. necessary adaptions of arguments for instantiation
            # pass the Runner if there's None:
            if item[1].get('runner', None) is None:
                item[1]['runner'] = self._runner

            if issubclass(item[0], ItemCommand):
                # commands need a 'cwd' or a 'repo' to run in.
                r_cwd = item[1].get('cwd')
                it_repo = item[1].get('repo')
                if not r_cwd and not it_repo:
                    raise InvalidTestRepoDefinitionError(
                        msg="Neither 'cwd' nor 'repo' was specified for {cl}. "
                            "At least one of those is required by ItemCommand:"
                            "{ls}{cl}({args})".format(ls=os.linesep,
                                                      cl=item[0].__name__,
                                                      args=item[1]),
                        repo=self.__class__,
                        item=item[0].__name__,
                        index=index
                    )

                # If 'repo' wasn't specified, we can try whether we already know
                # an ItemRepo at 'cwd' and pass it into 'repo'.
                # Note, that 'repo' isn't necessarily required by a command, but
                # most of them will need it and if not so, they just shouldn't
                # care, so we can safely pass one.
                if not it_repo:
                    repo_by_cwd = self._items.get(r_cwd)
                    if repo_by_cwd and isinstance(repo_by_cwd, ItemRepo):
                        # adjust definition, meaning we need to assign the
                        # relative path as if it was done by the user
                        item[1]['repo'] = r_cwd
                        it_repo = r_cwd

                # paths are relative in TestRepo definitions, but absolute in
                # the Item instances. Replace 'cwd' if needed.
                if r_cwd:
                    # store absolute path for instantiation
                    item[1]['cwd'] = os.path.normpath(opj(self._path, r_cwd))

                if it_repo:
                    # convert the reference in argument 'repo':
                    _path2item(item, index, 'repo')

                # convert item references in argument 'item':
                _path2item(item, index, 'item')

            if issubclass(item[0], ItemRepo) or issubclass(item[0], ItemFile):
                # paths are relative in TestRepo definitions, but absolute in
                # the Item instances. Replace them for instantiation, but keep
                # `r_path` for identification (key in the items dict).
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
                                                      cl=item[0].__name__,
                                                      args=item[1]),
                            repo=self.__class__,
                            item=item[0].__name__,
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
                                      cl=item[0].__name__,
                                      args=item[1]),
                            repo=self.__class__,
                            item=item[0].__name__,
                            index=index
                        )

                # store absolute path for instantiation
                item[1]['path'] = os.path.normpath(opj(self._path, r_path))

            # END path conversion
            # For ItemRepo and ItemFile the relative path is kept in `r_path`

            # special case ItemInfoFile
            if issubclass(item[0], ItemInfoFile):
                # pass TestRepo subclass to the info file:
                item[1]['class_'] = self.__class__
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
            if item[0] is ItemSelf:
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

        if not self.repo:
            raise InvalidTestRepoDefinitionError(
                msg="Definition must contain exactly one {cl}. Found none."
                    "".format(cl=ItemSelf),
                repo=self.__class__
            )

        # TODO: not sure yet whether or not we want to instantly and
        # unconditionally create, but think so ATM
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
        for item, index in zip(self._execution, range(len(self._execution))):
            try:
                item.create()
            except TestRepoCreationError as e:
                # add information the Item classes can't know:
                e.repo = self.__class__
                e.index = index
                raise e


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

# TODO: known_failure_XXX needs opt_arg 'testrepo' to pass the TestRepo
# class(es) the test does fail on.


#
#  Actual test repositories:
#


@auto_repr
class BasicGit(TestRepo_NEW):
    """Simple plain git repository

    RF'ing note: This resembles the old `BasicGitTestRepo`. The only difference
    is the content of INFO.txt, which is now more detailed. In particular it
    includes the entire definition of this test repository.
    """

    version = '0.1'

    _item_definitions = [(ItemSelf, {'path': '.',
                                     'annex': False}),
                         (ItemInfoFile, {'state': (ItemFile.ADDED,
                                                   ItemFile.UNMODIFIED)}),
                         (ItemFile, {'path': 'test.dat',
                                     'content': "123",
                                     'annexed': False,
                                     'state': (ItemFile.ADDED,
                                               ItemFile.UNMODIFIED)}),

                         (ItemCommit, {'cwd': '.',
                                       'item': ['test.dat', 'INFO.txt'],
                                       'msg': "Adding a basic INFO file and "
                                              "rudimentary load file."})
                         ]

    def __init__(self, path=None, runner=None):
        super(BasicGit, self).__init__(path=path, runner=runner)

    def assert_intact(self):

        # ###
        # Assertions to test object properties against what is defined:
        # ###
        eq_(len(self._items), 3)  # ItemRepo and ItemFile only
        assert_is_instance(self._items['.'], ItemSelf)
        assert_is_instance(self._items['test.dat'], ItemFile)
        assert_is_instance(self._items['INFO.txt'], ItemFile)

        # the top-level item `self.repo`
        assert(self.repo is self._items['.'])
        assert(self.repo.is_annex is False)
        assert(self.repo.is_git is True)

        for att in ['annex_version',
                    'is_direct_mode',
                    'annex_is_initialized',
                    'remotes',
                    'submodules',
                    'superproject']:
            value = self.repo.__getattribute__(att)
            assert(value is None,
                   "ItemSelf({p}).{att} is not None but: {v}"
                   "".format(p=self.repo.path, att=att, v=value))

        eq_([c[1] for c in self.repo.commits],
            ["Adding a basic INFO file and rudimentary load file."])
        # TODO: eq_(self.repo.branches, ['master'])

        # test.dat:
        test_dat = self._items['test.dat']
        assert_is_instance(test_dat, ItemFile)
        eq_(test_dat.path, opj(self.path, 'test.dat'))
        eq_(test_dat.content, "123")

        # INFO.txt:
        info_txt = self._items['INFO.txt']
        eq_(info_txt.path, opj(self.path, 'INFO.txt'))
        # Note: we can't compare the entire content of INFO.txt, since
        # it contains versions of git, git-annex, datalad. But some parts can
        # be expected and shouldn't change, so make assertions to indicate
        # integrity of the file's content:
        assert_is_instance(info_txt, ItemInfoFile)

        # both objects make up `files` of ItemSelf:
        eq_(set(self.repo.files), {test_dat, info_txt})

        # for both files the following should be true:
        for file_ in [test_dat, info_txt]:
            file_.assert_intact()
            assert(file_.is_clean is True)
            for att in ['annexed', 'is_modified', 'is_staged', 'is_untracked']:
                value = file_.__getattribute__(att)
                assert(value is False,
                       "ItemFile({p}).{att} is not False but: {v}"
                       "".format(p=file_.path, att=att, v=value))
            for att in ['annex_key', 'content_available', 'is_unlocked']:
                value = file_.__getattribute__(att)
                assert(value is None,
                       "ItemFile({p}).{att} is not None but: {v}"
                       "".format(p=file_.path, att=att, v=value))
            eq_(len(file_.commits), 1)
            eq_(file_.commits[0][1],
                "Adding a basic INFO file and rudimentary load file.")

        # ###
        # The objects' inner consistency and testing against what is physically
        # the case is done recursively via their respective assert_intact().
        # Note, that this requires to call assert_intact of all ItemRepo
        # instances in this TestRepo, that have no superproject.
        # In most cases this will just be one call to the toplevel instance:
        # ###
        # TODO: The note above might change a little, once it is clear what to
        # do about unregistered subs and untracked files.
        # TODO: May be that part can be done by TestRepo anyway, if it gets more
        # complicated. Then assert_intact wouldn't be abstract, but to be
        # enhanced.
        self.repo.assert_intact()


@auto_repr
class BasicMixed(TestRepo_NEW):
    """Simple mixed repository

    RF'ing note: This resembles the old `BasicAnnexTestRepo`. The only difference
    is the content of INFO.txt, which is now more detailed. In particular it
    includes the entire definition of this test repository.
    The renaming takes into account, that this repository has a file in git,
    which turns out to be not that "basic" as an annex with no file in git due
    to issues with annex repository version 6.
    """

    version = '0.1'

    _item_definitions = [(ItemSelf, {'path': '.',
                                     'annex': True}),
                         (ItemInfoFile, {'state': (ItemFile.ADDED,
                                                   ItemFile.UNMODIFIED)}),
                         (ItemFile, {'path': 'test.dat',
                                     'content': "123",
                                     'annexed': False,
                                     'state': (ItemFile.ADDED,
                                               ItemFile.UNMODIFIED)}),

                         (ItemCommit, {'cwd': '.',
                                       'item': ['test.dat', 'INFO.txt'],
                                       'msg': "Adding a basic INFO file and "
                                              "rudimentary load file for annex "
                                              "testing"}),
                         (ItemFile, {'path': 'test-annex.dat',
                                     'src': get_local_file_url(remote_file_path),
                                     'state': (ItemFile.ADDED,
                                               ItemFile.UNMODIFIED),
                                     'annexed': True,
                                     'key': "SHA256E-s28--2795fb26981c5a687b9bf44930cc220029223f472cea0f0b17274f4473181e7b.dat"
                                     }),
                         (ItemCommit, {'cwd': '.',
                                       'item': 'test-annex.dat',
                                       'msg': "Adding a rudimentary git-annex load file"}),
                         (ItemDropFile, {'cwd': '.',
                                         'item': 'test-annex.dat'})
                         ]

    def __init__(self, path=None, runner=None):
        super(BasicMixed, self).__init__(path=path, runner=runner)

    def assert_intact(self):
        # fake sth:
        assert "everything is fine"


class BasicAnnex(TestRepo_NEW):
    pass


# 4 times: untracked, modified, staged, all of them
class BasicGitDirty(BasicGit):
    pass




# see above (staged: annex, git, both)
class BasicAnnexDirty(BasicAnnex):
    pass


# ....


# v6 adjusted branch ...

# Datasets (.datalad/config, .datalad/metadata ...) ?