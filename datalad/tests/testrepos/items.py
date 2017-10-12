# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Items for test repository definitions
"""
import os
import shlex
from abc import ABCMeta, abstractmethod
from os.path import exists

from nose.tools import assert_is_instance, eq_, assert_in, assert_raises
from six import add_metaclass, string_types


from datalad import cfg, __version__
from datalad.cmd import GitRunner
from datalad.customremotes.base import init_datalad_remote
from datalad.dochelpers import borrowdoc, single_or_plural, exc_str
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError
from datalad.support.external_versions import external_versions
from datalad.support.network import get_local_file_url
from datalad.tests.testrepos.exc import InvalidTestRepoDefinitionError, \
    TestRepoCreationError
from datalad.utils import auto_repr, assure_list, on_windows
from .helpers import _excute_by_item


# TODO: Commands need to notify the ItemRepos! Otherwise we don't know what belongs where!
#       Same is true for instant file adding/committing
# TODO: runner calls need to set cwd! By default it's the TestRepo's runner, so cwd is its root!


# TODO: Commands for (special) remotes




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
    def url(self):
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
        self._items = set()  # ... of Item
        self._commits = set()  # ... of tuple (SHA, msg)
        self._branches = set()
        self._remotes = set()
        self._super = None  # ItemRepo

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
    def submodules(self, return_paths=False):
        items = [it for it in self._items
                 if isinstance(it, ItemRepo) and it.superproject is self]
        if return_paths:
            return [os.path.relpath(it.path, self.path) for it in items]
        else:
            return items

    @property
    def superproject(self):
        return self._super

    @property
    def files(self, return_paths=False):
        """Get the files known to this repo

        Parameters
        ----------
        return_paths: bool
            whether to return the paths of the files. ItemFile instances
            otherwise. Note, that paths are relative to ItemRepo's root.

        Returns
        -------
        list of ItemFile or str
        """
        items = [it for it in self._items if isinstance(it, ItemFile)]
        if return_paths:
            return [os.path.relpath(it.path, self.path) for it in items]
        else:
            return items

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

        _excute_by_item(cmd=create_cmd, item=self,
                        exc=TestRepoCreationError(
                            "Failed to create git repository")
                        )

        if self._src:
            # we just cloned
            self.remotes.add('origin')

        # we want to make it an annex
        if self._annex and self._annex_init:
            annex_cmd = ['git', 'annex', 'init']
            if self._annex_version:
                annex_cmd.append('--version=%s' % self._annex_version)

            _excute_by_item(cmd=annex_cmd, item=self,
                            exc=TestRepoCreationError(
                                "Failed to initialize annex")
                            )

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
                _excute_by_item(cmd=annex_cmd, item=self,
                                exc=TestRepoCreationError(
                                    "Failed to switch to direct mode")
                                )

            # TODO: Verify annex_version and annex_direct from .git/config
            # => might go into assert_intact

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

        [assert_is_instance(f_, ItemFile) for f_ in self.files]
        [assert_is_instance(r_, ItemRepo) for r_ in self.submodules]
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
    TYPECHANGED = 'T'  # Note: This one is missing in git-status short format according to its manpage
    UPDATED_BUT_UNMERGED = 'U'

    def __init__(self, path, repo, runner=None,
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
        repo: ItemRepo
            the repository this file is supposed to belong to (which is where it
            would be added when giving the respective state)
            This is required, since otherwise we would need to discover it from
            disc, which means that we would make what actually happened the
            definition of what was supposed to happen.
        """

        # TODO: Use constraints (like EnsureChoice for 'state') for sanity
        # checks on the arguments?

        if not path.startswith(repo.path):
            raise InvalidTestRepoDefinitionError(
                msg="'path' is not beneath the path of 'repo' for {it}({p})."
                    "".format(it=self.__class__,
                              p=path
                              ),
                item=self.__class__
            )

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
        self._repo = repo
        self._content = content
        self._state_index = state[0]
        self._state_worktree = state[1]
        self._commit_msg = commit_msg
        self._src = src
        self._locked = locked  # TODO: consider direct mode. There's no lock ...
        self._annexed = annexed
        self._key = key
        self._commits = set()
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

    def _get_annex_key_from_disc(self, exc=None):
        """get the key of the file as git-annex reports it

        Parameters
        ----------
        exc: TestRepoError
            predefined exception to raise instead of CommandError to give more
            information about when what item ran into the error.
        """
        lookup_cmd = ['git', 'annex', 'lookupkey', self._path]
        out, err = _excute_by_item(cmd=lookup_cmd, item=self, exc=exc)
        return out.strip()

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
                    msg="The following exception occurred while trying to write"
                        " to file {p}:{ls}{exc}".format(ls=os.linesep,
                                                        p=self.path,
                                                        exc=exc_str(e)
                                                        ),
                    item=self.__class__
                )

        # file actually exists now, add to repo:
        self._repo._items.add(self)

        # Furthermore, we can git-add, git-annex-add and commit the new file.
        # Anything more complex (like add, commit, change the content,
        # stage again, ...) cannot be achieved by create(), since this would
        # require way too complex definitions. That's what ItemCommand(item=...)
        # is for instead.

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
                add_cmd.extend(['--work-tree=.', 'add', self.path])

            _excute_by_item(cmd=add_cmd, item=self,
                            exc=TestRepoCreationError("Failed to add")
                            )

            if self._annexed:
                # we just annex-added. So the content is available ATM.
                self._content_present = True

            if self._annexed and not self._key:
                # look it up
                self._key = self._get_annex_key_from_disc(
                    exc=TestRepoCreationError("Failed to look up annex key")
                )

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

            _excute_by_item(cmd=unlock_cmd, item=self,
                            exc=TestRepoCreationError("Failed to unlock")
                            )

        if to_commit:
            if not self._commit_msg:
                self._commit_msg = "{it}: Added file {p} to {git_annex}" \
                                   "".format(it=self.__class__,
                                             p=self.path,
                                             git_annex="annex" if self._annexed
                                             else "git")
            commit_cmd = ['git', '--work-tree=.', 'commit',
                          '-m', '"%s"' % self._commit_msg,
                          '--', self.path]

            _excute_by_item(cmd=commit_cmd, item=self,
                            exc=TestRepoCreationError("Failed to commit")
                            )

            # get the commit's SHA for property:
            from .helpers import _get_last_commit_from_disc
            commit = _get_last_commit_from_disc(
                item=self,
                exc=TestRepoCreationError("Failed to look up commit SHA")
            )
            self._commits.add(commit)
            self._repo._commits.add(commit)

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

    def __init__(self, class_, repo, definition=None,
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
            path=path, repo=repo, runner=runner, content=content, state=state,
            commit_msg=commit_msg, annexed=annexed, src=src, locked=locked)


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

        _excute_by_item(cmd=self._cmd, item=self, cwd=self._cwd,
                        exc=TestRepoCreationError("Command failed")
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

        # now, get the commit and let the items know:
        from .helpers import _get_last_commit_from_disc
        commit = _get_last_commit_from_disc(item=self,
                                            exc=TestRepoCreationError(
                                                "Failed to look up commit SHA")
                                            )

        self._repo._commits.add(commit)
        for it in self._ref_items:
            it._commits.add(commit)
            it._state_index = ItemFile.UNMODIFIED
            # TODO: Does "git commit -- myfile" stage that file before?
            # If so: adjust it._state_worktree as well!

            # If ItemRepo didn't know about the committed items, it definitely
            # should now!
            self._repo._items.add(it)


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

