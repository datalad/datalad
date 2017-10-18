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
import logging
import os
import shlex
from abc import ABCMeta, abstractmethod
from os.path import exists, lexists, join as opj, isdir

from copy import deepcopy

from nose.tools import assert_is_instance, eq_, assert_in, assert_raises
from six import add_metaclass, string_types


from datalad import cfg, __version__
from datalad.cmd import GitRunner
from datalad.customremotes.base import init_datalad_remote
from datalad.dochelpers import borrowdoc, single_or_plural, exc_str
from datalad.support.annexrepo import AnnexRepo
from datalad.support.external_versions import external_versions
from datalad.support.network import get_local_file_url
from datalad.tests.testrepos.exc import InvalidTestRepoDefinitionError, \
    TestRepoCreationError, TestRepoAssertionError, TestRepoError
from datalad.utils import auto_repr, assure_list, on_windows
from .helpers import _excute_by_item
from .helpers import _get_last_commit_from_disc
from .helpers import _get_branch_from_commit
from .helpers import _get_remotes_from_config
from .helpers import _get_submodules_from_disc
from .helpers import _get_branches_from_disc
from .helpers import get_ancestry

from .helpers import _get_commits_from_disc
from datalad.utils import unique


lgr = logging.getLogger('datalad.tests.testrepos.items')


def log(*args, **kwargs):
    """helper to log at a default level

    since this is not even about actual datalad tests, not to speak of actual
    datalad code, log at pretty low level.
    """
    lgr.log(5, *args, **kwargs)


class Branch(object):

    def __init__(self, name, repo, commit=None, upstream=None,
                 points_to=None, is_active=False):
        """

        Parameters
        ----------
        name: str
        repo: ItemRepo
        commit: Commit or str
        upstream: Branch or str
        points_to: Branch or str
        is_active: bool
        """
        self.repo = repo
        self.name = name

        if commit is None:
            self._commit = self._commit_short = None
        elif isinstance(commit, Commit):
            self._commit = commit
        else:
            # assuming str (SHA)
            # could be long or short, but assume short and match in property
            # `commit` via startswith, so the full SHA would work, too. Note,
            # that we need to be robust against different lengths of short SHA
            # anyway.
            self._commit_short = commit
        if upstream is None:
            self._upstream = self._upstream_name = None
        elif isinstance(upstream, Branch):
            self._upstream = upstream
        else:
            # assume just name
            self._upstream_name = upstream

        if points_to is None:
            self._head_points_to = self._head_points_to_name = None
        elif isinstance(points_to, Branch):
            self._head_points_to = points_to
        else:
            # assume just name
            self._head_points_to_name = points_to

        self.is_active = is_active

    # TODO: setter
    @property
    def commit(self):
        """
        Returns
        -------
        Commit or None
        """

        if not self._commit:
            if self._commit_short:
                # search for it
                hit_commits = [c for c in self.repo.commits
                               if c.sha.startswith(self._commit_short)]
                if len(hit_commits) > 1:
                    raise TestRepoAssertionError(
                        msg="Branch '{self}': (Short) SHA collision in "
                            "{repo}({p}) for {short}:{ls}{commits}"
                            "".format(self=self.name,
                                      repo=self.repo,
                                      p=self.repo.path,
                                      short=self._commit_short,
                                      ls=os.linesep,
                                      commits=os.linesep.join(hit_commits))
                        )
                if not hit_commits:
                    raise TestRepoAssertionError(
                        msg="Branch '{self}': pointing to {short}, but commit "
                            "not found in {repo}({p})"
                            "".format(self=self.name,
                                      short=self._commit_short,
                                      repo=self.repo,
                                      p=self.repo.path)
                        )
                self._commit = hit_commits[0]

        return self._commit

    # TODO: setter
    @property
    def upstream(self):
        """
        Returns
        -------
        Branch or None
        """
        if not self._upstream:
            if self._upstream_name:
                # search for it
                hit_upstream = [b for b in self.repo.branches
                                if b.name == self._upstream_name]
                if len(hit_upstream) > 1:
                    raise TestRepoAssertionError(
                        msg="'{name}' is upstream for branch '{branch}', but "
                            "is ambiguous in {repo}({p}):{ls}{hits}"
                            "".format(name=self._upstream_name,
                                      branch=self.name,
                                      repo=self.repo,
                                      p=self.repo.path,
                                      ls=os.linesep,
                                      hits=os.linesep.join([b.name for b in
                                                            hit_upstream])
                                      )
                    )
                if not hit_upstream:
                    raise TestRepoAssertionError(
                        msg="'{name}' is upstream for branch '{branch}', but "
                            "isn't known by {repo}({p})"
                            "".format(name=self._upstream_name,
                                      branch=self.name,
                                      repo=self.repo,
                                      p=self.repo.path,
                                      )
                    )
                self._upstream = hit_upstream[0]
        return self._upstream

    # TODO: setter
    @property
    def points_to(self):
        """
        Returns
        -------
        Branch or None
        """
        if not self._head_points_to:
            if self._head_points_to_name:
                # search for it
                hit_branches = [b for b in self.repo.branches
                                if b.name == self._head_points_to_name]
                if len(hit_branches) > 1:
                    raise TestRepoAssertionError(
                        msg="'{name}' is registered to be pointed at by branch "
                            "'{branch}', but is ambiguous in {repo}({p}):"
                            "{ls}{hits}"
                            "".format(name=self._head_points_to_name,
                                      branch=self.name,
                                      repo=self.repo,
                                      p=self.repo.path,
                                      ls=os.linesep,
                                      hits=os.linesep.join([b.name for b in
                                                            hit_branches])
                                      )
                    )
                if not hit_branches:
                    raise TestRepoAssertionError(
                        msg="'{name}' is registered to be pointed at by branch "
                            "'{branch}', but isn't known by {repo}({p})"
                            "".format(name=self._head_points_to_name,
                                      branch=self.name,
                                      repo=self.repo,
                                      p=self.repo.path,
                                      )
                    )
                self._head_points_to = hit_branches[0]
        return self._head_points_to

    def copy_to(self, repo):
        # Note: copies references, but NOT the reference objects!
        # is_active always False!
        b = Branch(name=self.name,
                   repo=repo,
                   is_active=False)
        b._commit_short = self.commit.short,
        b._upstream_name = self.upstream.name
        b._head_points_to_name = self.points_to.name


class Commit(object):

    def __init__(self, sha, repo, short=None, parents=None, message=None,
                 paths=None):
        """
        Parameters
        ----------
        sha: str
        repo: ItemRepo
        short: str or None
        parents: str or Commit or list
        message: str or None
        paths: str or list or None
        """

        self.repo = repo
        self.sha = sha
        self.short = short
        self._parent_shas = []
        self._parents = []
        parents = assure_list(parents)
        # Note, that we might not yet be able to match a parent's SHA with an
        # actual Commit instance in `self.repo` at the moment we are creating
        # `self`.
        for p in parents:
            if isinstance(p, string_types):
                self._parent_shas.append(p)
            elif isinstance(p, Commit):
                self._parents.append(p)
        self.message = message  # property instead?
        self._paths = assure_list(paths)  # Note: relative to self.repo!

    # TODO: setter
    @property
    def parents(self):
        from_sha = [c for c in self.repo.commits
                    for p in self._parent_shas
                    if p == c.sha]
        assert(len(from_sha) == len(self._parent_shas))
        return unique(from_sha + self._parents)

    # TODO: setter
    @property
    def items(self):
        return [it for it in self.repo._items
                for p in self._paths
                if it.path == opj(self.repo.path, p)]

    def copy_to(self, repo):
        return Commit(sha=self.sha,
                      repo=repo,
                      short=self.short,
                      parents=[p.sha for p in self.parents],
                      message=self.message,
                      paths=self._paths)


@auto_repr
@add_metaclass(ABCMeta)
class Item(object):
    """(Partially abstract) base class for test repository definition items
    """

    def __init__(self, path, runner=None, check_definition=True):
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

    # TODO: abstractmethod is insufficient. The way Items call it, is actually
    # wrong currently, since derived classes wouldn't call super's one when
    # executing super's constructor! Implement a way to make sure, this is done
    # correctly.
    @abstractmethod
    def _check_definition(self, *args, **kwargs):
        pass

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

    # TODO: add an optional 'name' to use by ItemAddSubmodule

    def __init__(self, path, src=None, runner=None,
                 annex=True, annex_version=None, annex_direct=None,
                 annex_init=None, check_definition=True):
        """Initializes a new ItemRepo

        By default this comes with an extensive check on whether or not this
        ItemRepo's definition is valid and resulting in a ItemRepo physically
        creatable by its `create()` method.

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
        check_definition: bool
            whether or not to check for valid definition of the item. Disable
            only if you know what you are doing.
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

        # For now: check against datalad.config and raise if there's a
        # contradiction. A TestRepo can still have a mechanism to declare itself
        # invalid for certain configurations and avoid being created
        # (and thereby getting here) altogether.
        # The only issue might be that we cannot have mixed annex repo versions
        # ATM. It's determined by datalad.repo.version for all repos.
        from datalad import cfg
        version_from_config = cfg.obtain("datalad.repo.version")
        direct_from_config = cfg.obtain("datalad.repo.direct")

        if check_definition:
            self._check_definition(path=path, src=src, runner=runner,
                                   annex=annex, annex_version=annex_version,
                                   annex_direct=annex_direct,
                                   annex_init=annex_init,
                                   version_from_config=version_from_config,
                                   direct_from_config=direct_from_config)

        if annex and annex_init is None:
            annex_init = True

        super(ItemRepo, self).__init__(path=path, runner=runner,
                                       check_definition=check_definition)

        # generally we have a valid definition now
        # set unspecified parameters from datalad config
        if annex_version is None:
            annex_version = version_from_config
        if annex_direct is None:
            annex_direct = direct_from_config

        self._src = src
        self._annex = annex
        self._annex_version = annex_version if annex else None
        self._annex_direct = annex_direct if annex else False
        self._annex_init = annex_init if annex else False

        # TODO: we must not use set; let it be lists and use datalad.utils.unique
        self._items = []  # ... of Item
        self._commits = []  # ... of Commit
        self._branches = [] # ... of Branch
        self._remotes = []  # ... of tuple (name, url)  # For now
        self._super = None  # ItemRepo
        self._created_items = []  # additional items instantiated during creation # TODO: should that be an actual attribute? Can be local for create(), I guess
        self._is_initialized = False  # not yet created/initialized

    @property
    def src(self):
        # self._src might be a callable:
        return self._src() if self._src and \
                              not isinstance(self._src, ItemRepo) else self._src

    @property
    def branches(self):
        # For easier comparison within assert_intact as well as within actual
        # datalad tests, exclude 'HEAD' from being returned as a branch.
        return [b for b in self._branches if b.name != 'HEAD']

    @property
    def head(self):
        candidates = [b for b in self._branches if b.name == 'HEAD']
        if len(candidates) > 1:
            raise TestRepoError(msg="Found more than one 'HEAD' in {repo}"
                                    "".format(repo=self),
                                item=self.__class__)
        elif not candidates:
            return None
        else:
            return candidates[0]

    def _update_from_src(self, src=None):
        """update all information `self` retrieved the moment it was cloned from
        self.src (or submodule-update'd instead of git-clone'd)
        """

        # TODO: We probably need to RF further and consider to use (most of)
        # this for an update after fetch/pull, too!

        if src is None:
            src = self.src

        self._annex = src.is_annex

        # we cloned, so we have a remote 'origin':
        # TODO: can that be different if were submodule-update'd?
        #       -> However: it can once we also consider fetch/pull
        self._remotes.add(('origin', src.url))

        #
        # ### branches and their commits: ###
        #
        branches_to_add = []
        commits_to_add = []
        # Whether we got here by git-clone or git-submodule-update, we get all
        # local branches from src:
        for src_branch in src.branches:
            # except remote branches in src:
            if src_branch.name.startswith('remotes/'):
                continue
            branches_to_add.append(Branch(name='remotes/origin/' + src_branch.name,
                                          repo=self,
                                          commit=src_branch.commit.sha,
                                          upstream=None,
                                          points_to=None,
                                          is_active=False))
            # we need the commit that branch is pointing to and its ancestry:
            commits_to_add.extend([c.copy_to(self) for c in
                                   get_ancestry(src_branch.commit)])

        # Now HEAD:
        # derive our 'HEAD' from src:
        if self.superproject is not None:
            # we are a submodule already, so it wasn't cloning but
            # submodule-update.
            # -> HEAD is detached
            # -> HEAD is active branch
            # Note: We are considering default update only for now.
            # Theoretically, we can have a submodule-update using merge/rebase
            # or whatever strategy. This would change things.
            # TODO: The note above is just another reason to RF this into more
            # fine-grained pieces.
            head_points_to = None
            head_active = True
        else:
            # assuming clone:
            head_points_to = src.head.points_to
            head_active = False

        branches_to_add.append(Branch(name='HEAD',
                                      repo=self,
                                      commit=src.head.commit.sha,
                                      upstream=None,
                                      points_to=head_points_to.name,
                                      is_active=head_active))
        if src.head.points_to:
            # src.head points to an actual branch, that's the one we now have as
            # a local branch
            hit_branches = [b for b in src.branches
                            if b.name == src.head.points_to.name]
            assert(len(hit_branches) == 1)
            local_branch = hit_branches[0]
            branches_to_add.append(Branch(name=local_branch.name,
                                          repo=self,
                                          commit=local_branch.commit.sha,
                                          upstream='remotes/origin/' + local_branch.name,
                                          points_to=None,
                                          is_active=not head_active))
        else:
            # src is at detached HEAD
            pass

        # we need the commit HEAD is pointing to and its ancestry:
        commits_to_add.extend([c.copy_to(self) for c in
                               get_ancestry(src.head.commit)])

        # we got all the commits from the branches we got backwards;
        # TODO: Make sure, this is correct. It would mean to exclude commits in
        # src, that are part of remote branches only (from the POV of src). It
        # also would exclude detached commits in src, that are not reachable by
        # exploring the history of branches we got.
        # Is this true for git-clone/git-submodule-update?
        # Otherwise we need to add relevant commits here.

        #
        # items:
        #
        # Based on the commits we retrieved, we know what files and submodules
        # to get
        items_to_add = []
        for c in commits_to_add:
            for it in c.items:
                new_path = opj(self.path, os.path.relpath(it.path, src.path))
                if new_path in [n.path for n in items_to_add]:
                    # we got it already
                    continue
                if issubclass(it, ItemRepo):
                    # we got a submodule. However, keep in mind we are updating
                    # `self` after cloning or submodule-update, meaning that
                    # this is a non-initialized one and we barely know anything
                    # about it. This is what needs to be represented in the
                    # corresponding item.
                    new = ItemRepo(path=new_path,
                                   src=it,
                                   annex=it.is_annex,
                                   annex_version=None, # TODO: do we inherit anything from self or it or src here?
                                   annex_direct=None, # TODO: do we inherit anything from self or it or src here?
                                   annex_init=None,  # TODO: do we inherit anything from self or it or src here?
                                   check_definition=True  # not sure yet
                                   )
                    new._is_initialized = False
                    new._super = self
                    items_to_add.append(new)
                elif issubclass(it, ItemFile):
                    # we got a file
                    # Note, that we got it by cloning and therefore can't just
                    # copy everything
                    new = ItemFile(path=new_path,
                                   repo=self,
                                   content=it.content,
                                   state=(ItemFile.UNMODIFIED, ItemFile.UNMODIFIED),
                                   annexed=it.annexed,
                                   key=it.key,
                                   src=None,
                                   locked=None,  # TODO: tricky with V6
                                   check_definition=True  # not sure yet
                                   )
                    new._content_present = False if it.annexed else None
                    items_to_add.append(new)
                else:
                    # WTF?
                    raise TestRepoCreationError(
                        msg="Unexpected item class {it}({p}) referenced when"
                            "updating {self}({p2}).".format(it=it.__class__,
                                                            p=it.path,
                                                            self=self,
                                                            p2=self.path),
                        item=self.__class__
                    )

        # TODO: Are we missing some cross references?
        self._branches.extend(branches_to_add)
        self._commits.extend(commits_to_add)
        self._items.extend(items_to_add)

        return items_to_add

    def _check_definition(self, path, src, runner, annex, annex_version,
                          annex_direct, annex_init,
                          version_from_config, direct_from_config):

        log("Processing definition of %s(%s)", self.__class__, path)

        # just to be sure, check v6 vs direct mode conflict
        # TODO: Actually, this is per test build - no need to test for every
        # repo; Move somewhere else
        if version_from_config >= 6 and direct_from_config:
            raise InvalidTestRepoDefinitionError(
                msg="Invalid datalad configuration. There is no direct mode, "
                    "if you use annex repository version 6 or greater.",
                item=self.__class__
            )

        if src is not None and \
                not isinstance(src, ItemRepo) and \
                not callable(src):
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'src' is expected to be an ItemRepo or a "
                    "callable returning an ItemRepo but was: {src}"
                    "".format(src=src),
                item=self.__class__
            )

        if annex_version is not None and annex_version != version_from_config:
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'annex_version' (v{vp})conflicts with datalad's "
                    "configuration in \"datalad.repo.version\" (v{vc})"
                    "".format(vp=annex_version, vc=version_from_config),
                item=self.__class__
            )

        if annex_direct is not None and direct_from_config != annex_direct:
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'annex_direct' ({dp})conflicts with datalad's "
                    "configuration in \"datalad.repo.direct\" ({dc})"
                    "".format(dp=annex_direct, dc=direct_from_config),
                item=self.__class__
            )

        if not annex and (annex_version or annex_direct or annex_init):
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="Parameters 'annex_version' or 'annex_direct' or "
                    "'annex_init' were specified, while 'annex' wasn't True."
            )

        if annex and annex_init is False and not src:
            raise InvalidTestRepoDefinitionError(
                msg="A non-initialized annex must be created by cloning. "
                    "'annex_init' must not be False while no 'src' is given.",
                item=self.__class__
            )

        if annex and annex_version and annex_direct and annex_version >= 6:
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="There is no direct mode, if you use annex repository "
                    "version 6 or greater."
            )
        if annex_init is False and (annex_version or annex_direct):
            # Note, that this is about test repos! They are used within the
            # tests by actual datalad code. That code cannot respect what is
            # specified herein regarding the possible initialization of that
            # repo.
            raise InvalidTestRepoDefinitionError(
                item=self.__class__,
                msg="Parameters 'annex_version' or 'annex_direct' were "
                    "specified, while 'annex_init' wasn't True."
            )

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

    @property
    def commits(self):
        return self._commits


    # TODO: How to represent remotes? Just the names or names plus url(s)?
    # What about special remotes?
    @property
    def remotes(self):
        # Note: names and url(s)
        return self._remotes

    @property
    def submodules(self, return_paths=False):  # doesn't work; see files
        items = [it for it in self._items
                 if isinstance(it, ItemRepo) and it.superproject is self]
        if return_paths:
            return [os.path.relpath(it.path, self.path) for it in items]
        else:
            return items

    @property
    def superproject(self):
        return self._super

    def get_files(self, return_paths=False):
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

    @property
    def files(self):
        return self.get_files(return_paths=False)

    def _call_annex_init(self):

        annex_cmd = ['git', 'annex', 'init']
        if self._annex_version:
            annex_cmd.append('--version=%s' % self._annex_version)

        _excute_by_item(cmd=annex_cmd, item=self,
                        exc=TestRepoCreationError(
                            "Failed to initialize annex")
                        )

        self._branches.add('git-annex')
        # if we are on a fresh clone of direct mode src, we had
        # 'annex/direct/master' (or whatever HEAD) and now got the actual
        # 'master' in addition. Note, that this may be different if direct mode
        # is enforced by annex itself and therefore during annex-init. This
        # might prevent 'master' from coming alive.
        # TODO: double check on windows!
        # For now, simply:
        if 'annex/direct/master' in self.branches and \
                len([b for b in self.branches
                     if not b.startswith('remotes/')]) == 2:
            # just added git-annex and nothing but annex/direct/master before
            # TODO: still wrong. If it's at detached HEAD ...
            self._branches.add('master')

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
            # TODO: self._remotes.add(('datalad', {'annex-externaltype': 'datalad'}))
            self._remotes.add(('datalad', ''))

        if self._annex_direct:
            annex_cmd = ['git', 'annex', 'direct']
            _excute_by_item(cmd=annex_cmd, item=self,
                            exc=TestRepoCreationError(
                                "Failed to switch to direct mode")
                            )
            # TODO: we need to figure out what branch HEAD is pointing to or
            # what branch we just cloned from self.src. For now, just go
            # for 'master':
            self._branches.add('annex/direct/master')
        else:
            # TODO: we didn't want direct mode (False) or didn't care (None).
            # check whether it was enforced by annex and adjust attribute or
            # raise
            pass

    def create(self):
        """Creates the physical repository
        """

        log("Creating %s(%s)", self.__class__, self.path)

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
        create_cmd.extend(['clone', self.src.url, os.curdir]
                          if self.src else ['init'])

        _excute_by_item(cmd=create_cmd, item=self,
                        exc=TestRepoCreationError(
                            "Failed to create git repository")
                        )
        self._is_initialized = True

        if self.src:
            # we just cloned
            self._created_items.update(self._update_from_src())

        # we want to make it an annex
        if self._annex and self._annex_init:
            self._call_annex_init()

        return self._created_items

    def assert_intact(self):
        """This supposed to make basic tests on whether or not what is stored in
        this ItemRepo instance actually is, what can be found on disc plus some
        consistency checks for the object itself.
        Everything else is out of scope and needs to be tested by ItemRepo and
        the subclasses of TestRepo.
        """

        log("Integrity check for %s(%s)", self.__class__, self.path)

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
            if not self.annex_is_initialized:
                # This needs to be a clone
                assert(self.src)
                assert(('origin', self.src) in self.remotes)
            else:
                # TODO: V6 adjusted branch
                any(b == 'git-annex' or 'annex/direct' in b
                    for b in self.branches)

        if self.src and self._is_initialized:
            # Note: self.src indicates that we cloned the repo from somewhere.
            # Therefore we have 'origin'. Theoretically there could be an
            # ItemCommand that removed that remote, but left self.src.
            # If that happens, that ItemCommand probably should be adapted to
            # also remove self.src.
            assert(self.remotes)

        assert_is_instance(self.branches, set)
        [assert_is_instance(b, string_types) for b in self.branches]

        if self.branches:
            assert self.commits
            # TODO: Not necessarily vice versa? Could be just detached HEAD, I guess

        assert_is_instance(self.commits, set)
        for c in self.commits:
            assert_is_instance(c, tuple)
            eq_(len(c), 2)
            assert_is_instance(c[0], string_types)  # SHA
            assert_is_instance(c[1], string_types)  # message

        assert_is_instance(self.files, list)
        [assert_is_instance(f_, ItemFile) for f_ in self.files]
        for it in self.files:
            assert(it.path.startswith(self.path))
            assert(it._repo is self)
            it.assert_intact()
            # Note: Not actually sure how this would look if there were files
            # moved from one repo to another within the testrepo setup. In case
            # we ever get there: Reconsider whether this should be true:
            [assert_in(commit, self.commits) for commit in it.commits]

        assert_is_instance(self.submodules, list)
        [assert_is_instance(r_, ItemRepo) for r_ in self.submodules]
        for it in self.submodules:
            assert(it.path.startswith(self.path))
            assert(it.superproject is self)
            it.assert_intact()
            # TODO: For now, there is no place to easily check for commits that
            # changed submodules (not commits WITHIN them)

        # physical appearance:

        # TODO: Is it reasonable to record mtime of self.path, self.path/.git, etc.?
        # Consider Yarik's comment on that in PR #1899!

        assert(exists(self.path))
        assert(isdir(self.path))

        if self._is_initialized:
            # it's a valid repository:
            assert(exists(opj(self.path, '.git')))

            # TODO: files! listdir ... But: ignore .git/, .gitmodules, ...

            # branches
            branches_from_disc = _get_branches_from_disc(
                item=self,
                exc=TestRepoAssertionError("Failed to look up branches")
            )
            eq_(set(branches_from_disc), self.branches)
            # TODO: are branches pointing to and containing the right commits?

            # state: tested on a per file basis?
            #        may be some overall test? (ignore submodules)

            # commits (partly done. If they involve a file this should have been tested by ItemFile.assert_intact)
            #         Q: What else? submodules => same as above
            #         Can there possibly be more?
            # TODO: Test commit tree? Requires to represent that structure somehow

            # submodules
            submodules_from_disc = _get_submodules_from_disc(
                item=self,
                exc=TestRepoAssertionError("Failed to look up submodules")
            )
            # TODO: We don't store everything in ItemRepo yet, so for now just look
            # at the paths:
            eq_(set([os.path.relpath(sm.path, self.path) for sm in self.submodules]),
                set([sm[2] for sm in submodules_from_disc]))

            # superproject
            # No need to test physically, since we have tested that superproject
            # points to self for all submodules and we just tested the other
            # direction (submodules)

            # remotes
            # TODO: Generally represent remotes in ItemRepo in full and have some in actual TestRepos
            try:
                remotes_from_disc = _get_remotes_from_config(self)
            except Exception as e:
                raise TestRepoAssertionError(
                    msg="Failed to read remotes for {r}({p}): {exc}"
                        "".format(r=self.__class__,
                                  p=self.path,
                                  exc=exc_str(e)),
                    item=self.__class__
                )

            # just names for now (see TODO)
            eq_(set([r[0] for r in remotes_from_disc]),
                set([r[0] for r in self.remotes]))

            # TODO: files: locked/unlock must be bool if repo is not in direct mode
            # and file is annexed. ItemFile doesn't know about direct mode.

        else:
            # not initialized
            assert(not exists(opj(self.path, '.git')))

        if self.is_annex and self._is_initialized and self.annex_is_initialized:
            # either .git is a dir and has an annex subdir or it's a file
            # pointing to a dir with an annex subdir

            # Note: This function is actually copied from AnnexRepo, but doesn't
            # use anything from datalad
            def git_file_has_annex(p):
                """Return True if `p` contains a .git file, that points to a git
                dir with a subdir 'annex'"""
                _git = opj(p, '.git')
                if not os.path.isfile(_git):
                    return False
                with open(_git, "r") as f:
                    line = f.readline()
                    if line.startswith("gitdir: "):
                        return exists(opj(p, line[8:], 'annex'))
                    else:
                        raise TestRepoAssertionError(
                            msg="Invalid .git-file {p}.".format(p=p)
                        )

            assert(exists(opj(self.path, '.git', 'annex')) or
                   git_file_has_annex(self.path))

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
                 annexed=False, key=None, src=None, locked=None,
                 check_definition=True):
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
        check_definition: bool
            whether or not to check for valid definition of the item. Disable
            only if you know what you are doing.
        """

        if check_definition:
            self._check_definition(path=path, repo=repo, runner=runner,
                                   content=content, state=state,
                                   commit_msg=commit_msg, annexed=annexed,
                                   key=key, src=src, locked=locked)

        super(ItemFile, self).__init__(path=path, runner=runner,
                                       check_definition=check_definition)
        self._repo = repo
        self._content = content
        self._state_index = state[0]
        self._state_worktree = state[1]
        self._commit_msg = commit_msg
        self._src = src
        self._locked = locked  # TODO: consider direct mode. There's no lock ...
        self._annexed = annexed
        self._key = key
        self._content_present = None  # to be set when actually adding the file
                                      # to annex

    def _check_definition(self, path, repo, runner,
                          content, state, commit_msg,
                          annexed, key, src, locked):

        log("Processing definition of %s(%s)", self.__class__, path)

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
        return (not self._locked) if self._locked is not None else None

    @property
    def is_locked(self):
        return self._locked

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
        # TODO: derive from self.repo instead!
        return [c for c in self._commits]

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

        log("Creating %s(%s)", self.__class__, self.path)

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
            log("Add %s(%s) to %s", self.__class__, self.path, self._repo)
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
            log("Unlock %s(%s)", self.__class__, self.path)
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
            log("Committing %s(%s)", self.__class__, self.path)
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
            commit = _get_last_commit_from_disc(
                item=self,
                exc=TestRepoCreationError("Failed to look up commit SHA")
            )
            self._commits.add(commit)
            self._repo._commits.add(commit)

            # we may have just created a branch 'repo' should know about. In
            # particular when this is the first commit ever and thereby
            # "creating" 'master'.
            # get the branch and notify repo, that it has that branch:
            branches = _get_branch_from_commit(item=self, commit=commit[0],
                                               exc=TestRepoCreationError(
                                                   "Failed to look up branch")
                                               )
            if len(branches) > 1:
                # we just simply committed. It couldn't rightfully end up in
                # several branches
                raise TestRepoCreationError(
                    msg="Unexpectedly found commit {cmt} in multiple branches: "
                        "{branches}".format(cmt="%s (%s)" % commit,
                                            branches=branches),
                    item=self.__class__
                )
            self._repo._branches.add(branches[0])

    def assert_intact(self):
        """This supposed to make basic tests on whether or not what is stored in
        this ItemFile instance actually is, what can be found on disc plus some
        consistency checks for the object itself.
        Everything else is out of scope and needs to be tested by ItemRepo and
        the subclasses of TestRepo.
        """

        log("Integrity check for %s(%s)", self.__class__, self.path)

        # object consistency

        assert(os.path.isabs(self.path))
        assert_is_instance(self.content, string_types)
        assert_is_instance(self.annexed, bool)
        assert_is_instance(self.is_untracked, bool)
        assert_is_instance(self.is_staged, bool)
        assert_is_instance(self.is_modified, bool)
        assert_is_instance(self.is_clean, bool)

        states = [ItemFile.UNTRACKED,
                  ItemFile.UNMODIFIED,
                  ItemFile.MODIFIED,
                  ItemFile.ADDED,
                  ItemFile.DELETED,
                  ItemFile.RENAMED,
                  ItemFile.COPIED,
                  ItemFile.TYPECHANGED,
                  ItemFile.UPDATED_BUT_UNMERGED]
        assert(self._state_index in states)
        assert(self._state_worktree in states)

        if self.is_untracked:
            assert(self.is_staged is False)
            assert(self.is_modified is False)
            assert(self.is_clean is False)
            assert(self.is_locked is None)
            assert(self.is_unlocked is None)

            assert(not self.commits)
            assert(self.annexed is False)
            assert(self.annex_key is None)
            assert(self.content_available is None)

        if self.is_modified or self.is_staged:
            assert(self.is_clean is False)
            assert(self.is_untracked is False)

        if self.is_clean:
            assert(self.is_untracked is False)
            assert(self.is_staged is False)
            assert(self.is_modified is False)

        # if it's neither untracked nor staged as a new file, there needs to be
        # a commit and vice versa:
        assert((self._state_index in [ItemFile.UNMODIFIED,
                                 ItemFile.MODIFIED,
                                 ItemFile.DELETED,
                                 ItemFile.RENAMED,
                                 ItemFile.COPIED,
                                 ItemFile.TYPECHANGED,
                                 ItemFile.UPDATED_BUT_UNMERGED]
                and isinstance(self.commits, list)
                ) or
               (self._state_index in [ItemFile.UNTRACKED, ItemFile.ADDED]
                and not self.commits
                )
               )

        if self.is_locked or self.is_unlocked \
                or self.annex_key or self.content_available:
            assert self.annexed

        if self.annexed:
            assert(self.is_untracked is False)
            assert_is_instance(self.annex_key, string_types)
            assert_is_instance(self.content_available, bool)
            assert_is_instance(self.commits, list)

        # Note: `None` if "locked/unlocked" isn't a valid concept (plain git,
        # untracked, direct mode):
        assert(not(self.is_locked and self.is_unlocked))
        assert(not(self.is_locked is False and self.is_unlocked is False))

        # physical appearance:

        assert(lexists(self.path))

        if self.content_available or not self.annexed:
            with open(self.path, 'r') as f:
                content_from_disc = f.read()
            eq_(content_from_disc, self.content)

        if self.is_locked:
            assert_raises(EnvironmentError, open, self.path, 'w')

        # TODO: if not self.is_untracked: git knows it
        # TODO: if self.annexed: annex finds it and provides a key
        # TODO: compare commits
        # TODO: - state? This might need annex-proxy and ignore-submodules, but
        #         since we have a certain file to specify it might work
        #       - see corresponding note in ItemRepo


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

        log("Processing definition of %s(%s)", self.__class__, path)

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


# TODO: Commands for (special) remotes

@auto_repr
class ItemCommand(Item):
    """Base class for commands to be included in TestRepo's definition

    Also provides a generic call to an arbitrary command. Use with caution!
    Since it's generic it doesn't know in what way it might manipulate any items
    and therefore can't set their properties accordingly.
    """

    def __init__(self, cmd, runner=None, item=None, cwd=None, repo=None,
                 check_definition=True):
        """

        Parameters
        ----------
        runner: Runner or None
        cmd: list
        item: Item or list of Item or None
        cwd: str or None
        repo: ItemRepo or None
        """

        if check_definition:
            ItemCommand._check_definition(self, cmd=cmd, runner=runner,
                                          item=item, cwd=cwd, repo=repo)

        # if `cwd` wasn't specified, use root of `repo`
        if not cwd:
            cwd = repo.path

        super(ItemCommand, self).__init__(path=cwd, runner=runner,
                                          check_definition=check_definition)

        if isinstance(cmd, string_types):
            self._cmd = shlex.split(cmd, posix=not on_windows)
        else:
            self._cmd = cmd

        self._ref_items = assure_list(item)
        self._cwd = cwd
        self._repo = repo

        # if items were passed, append them:
        if self._ref_items:
            self._cmd.append('--')
            self._cmd.extend([it.path for it in self._ref_items])

    def _check_definition(self, cmd, runner, item, cwd, repo):

        log("Processing definition of %s", self.__class__)
        if not isinstance(cmd, string_types + (list,)):
            raise InvalidTestRepoDefinitionError(
                msg="Parameter 'cmd' is expected to be a list or a string."
                    "Found {type}: {cmd}"
                    "".format(type=type(cmd),
                              cmd=cmd
                              ),
                item=ItemCommand
            )

    def create(self):
        """Default implementation to run `self._cmd`

        May (and probably SHOULD) be overridden by subclasses. While it can be
        used by subclasses to run the actual command, they should at least
        extend it to modify properties of involved Items.
        """
        log("Executing %s in %s", self.__class__, self.path)

        _excute_by_item(cmd=self._cmd, item=self, cwd=self._cwd,
                        runner=self._runner,
                        exc=TestRepoCreationError("Command failed")
                        )


@auto_repr
class ItemCommit(ItemCommand):
    """Item to include an explicit call to git-commit in TestRepo's definition

    This is needed in particular when you want to commit several Items at once,
    which can't be done via their definitions, since they don't know each other
    or the ItemRepo they belong to.
    """

    def __init__(self, runner, item=None, cwd=None, msg=None, repo=None,
                 check_definition=True):

        item = assure_list(item)

        if check_definition:
            self._check_definition(runner=runner, item=item, cwd=cwd, msg=msg,
                                   repo=repo)

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
                      '-m', '%s' % msg]
        # Note, that items will be appended by super class

        super(ItemCommit, self).__init__(runner=runner, item=item, cwd=cwd,
                                         cmd=commit_cmd, repo=repo,
                                         check_definition=check_definition)

    def _check_definition(self, runner, item, cwd, msg, repo):
        log("Processing definition of %s", self.__class__)

        if not repo:
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is required. By default this could "
                    "also be derived from 'cwd' by the TestRepo (sub-)class, "
                    "but apparently this didn't happen."
                    "".format(it=self.__class__),
                item=self.__class__
            )

    def create(self):

        log("Executing %s in %s", self.__class__, self.path)

        # run the command:
        super(ItemCommit, self).create()

        # now, get the commit and let the items know:
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

        # we may have just created a branch 'repo' should know about. In
        # particular when this is the first commit ever and thereby "creating"
        # 'master'.
        # get the branch and notify repo, that it has that branch:
        branches = _get_branch_from_commit(item=self, commit=commit[0],
                                           exc=TestRepoCreationError(
                                               "Failed to look up branch")
                                           )
        if len(branches) > 1:
            # we just simply committed. It couldn't rightfully end up in several
            # branches
            raise TestRepoCreationError(
                msg="Unexpectedly found commit {cmt} in multiple branches: "
                    "{branches}".format(cmt="%s (%s)" % commit,
                                        branches=branches),
                item=self.__class__
            )
        self._repo._branches.add(branches[0])


@auto_repr
class ItemDropFile(ItemCommand):
    """Item to include an explicit call to git-annex-drop in TestRepo's
    definition
    """

    def __init__(self, runner, item=None, cwd=None, repo=None,
                 check_definition=True):

        item = assure_list(item)

        if check_definition:
            self._check_definition(runner=runner, item=item, cwd=cwd, repo=repo)

        # build command call:
        drop_cmd = ['git', 'annex', 'drop']

        super(ItemDropFile, self).__init__(cmd=drop_cmd, runner=runner,
                                           item=item, cwd=cwd, repo=repo,
                                           check_definition=check_definition)

    def _check_definition(self, runner, item, cwd, repo):

        log("Processing definition of %s", self.__class__)

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
                    " {repo}".format(it=self.__class__,
                                      repo=str(repo)),
                item=self.__class__
            )

    def create(self):

        log("Executing %s in %s", self.__class__, self.path)

        # run the command:
        super(ItemDropFile, self).create()

        # notify files:
        for it in self._ref_items:
            it._content_present = False


@auto_repr
class ItemAddSubmodule(ItemCommand):

    def __init__(self, runner, item=None, cwd=None, repo=None,
                 commit=False, commit_msg=None,
                 check_definition=True):
        """Add ItemRepo(s) as submodule(s) to another one in-place.

        Note, that the ItemRepo to add has to exist as such already - you can't
        directly clone from an arbitrary URL with this command. If you need to
        clone from a remote location, do so when creating the ItemRepo.

        Parameters
        ----------
        runner: Runner
        item: ItemRepo or list of ItemRepo or None
            repo(s) to add as submodules
        cwd: str or None
        repo: ItemRepo
            repo to add the submodules to
        commit: bool
            whether or not to commit the addition afterwards
        commit_msg: str
            message to use for committing if `commit` was True
        """

        item = assure_list(item)

        if check_definition:
            self._check_definition(runner=runner, item=item, cwd=cwd, repo=repo,
                                   commit=commit, commit_msg=commit_msg)

        # Note: We need several calls - can't append items to the command call
        # via '--'. That means, when we pass `item` to super's constructor, the
        # command call build therein is wrong. Since we need to override
        # `create()` anyway and change the actual call for each item, the
        # wrongly built `self._cmd` doesn't actually matter. Just be aware of
        # it, when changing this implementation.
        cmd = ['git', '--work-tree=.', 'submodule', 'add']
        super(ItemAddSubmodule, self).__init__(cmd, runner=runner, item=item,
                                               cwd=cwd, repo=repo,
                                               check_definition=check_definition)
        # Cut self._cmd back (see the note above)
        self._cmd = self._cmd[:4]

        self._commit = commit
        self._commit_msg = commit_msg

    def _check_definition(self, runner, item, cwd, repo, commit, commit_msg):

        log("Processing definition of %s", self.__class__)

        if not repo:
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is required. By default this could "
                    "also be derived from 'cwd' by the TestRepo (sub-)class, "
                    "but apparently this didn't happen."
                    "".format(it=self.__class__),
                item=self.__class__
            )

        if not isinstance(repo, ItemRepo):
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'repo' is not an ItemRepo:"
                    " {repo}".format(it=self.__class__,
                                     repo=str(repo)),
                item=self.__class__
            )

        if not item:
            raise InvalidTestRepoDefinitionError(
                msg="{it}: Parameter 'item' required to specify the repository "
                    "to be added as a submodule. It's expected to be an "
                    "ItemRepo or a list thereof."
                    "".format(it=self.__class__),
                item=self.__class__
            )

        for it in item:
            if not isinstance(it, ItemRepo):
                raise InvalidTestRepoDefinitionError(
                    msg="Item in parameter 'item' is not an ItemRepo: {it}"
                        "".format(it=str(it)),
                    item=self.__class__
                )

    def create(self):

        log("Executing %s in %s", self.__class__, self.path)

        for it in self._ref_items:

            # we need to use the relative path for the path to add as submodule
            # and its "url" as well.
            import posixpath
            from datalad.utils import posix_relpath

            r_path = os.path.relpath(it.path, self._repo.path)
            url = posixpath.join(os.curdir, posix_relpath(it.path, self._cwd))

            # build actual command call and execute
            cmd = self._cmd + [url, r_path]
            _excute_by_item(cmd=cmd, item=self, runner=self._runner,
                            cwd=self._cwd,
                            exc=TestRepoCreationError(
                                msg="submodule-add failed for {it}({p})"
                                    "".format(it=it, p=it.path),
                                item=self)
                            )

            # notify items:
            it._super = self._repo
            self._repo._items.add(it)

        if self._commit:
            # used in commit- and error-message
            list_of_subs = "{space}{subs}" \
                           "".format(
                            space=single_or_plural(" ", os.linesep,
                                                   len(self._ref_items)),
                            subs=os.linesep.join(
                                         ["%s(%s)" % (it, it.path)
                                          for it in self._ref_items]
                                 )
                            )

            if not self._commit_msg:
                # build default message:
                msg = "{cmd}: Added {sub_s}:".format(cmd=self,
                                                     sub_s=single_or_plural(
                                                         "submodule",
                                                         "submodules",
                                                         len(self._ref_items))
                                                     )
                msg += list_of_subs
            else:
                msg = self._commit_msg

            # TODO: explict list of subs + .gitmodules

            cmd = ['git', '--work-tree=.', 'commit', '-m', msg]
            _excute_by_item(cmd=cmd, item=self, runner=self._runner,
                            cwd=self._cwd,
                            exc=TestRepoCreationError(
                                msg="Failed to commit submodules:" +
                                    list_of_subs,
                                item=self)
                            )
            self._repo._commits.add(_get_last_commit_from_disc(
                item=self,
                exc=TestRepoCreationError("Failed to look up commit SHA")))


@auto_repr
class ItemUpdateSubmodules(ItemCommand):

    def __init__(self, repo, init=False, runner=None, cwd=None, check_definition=True):
        """

        :param init: bool
        :param runner:
        :param cwd:
        :param repo:
        :param check_definition:
        :return:
        """

        if check_definition:
            self._check_definition(init=init, runner=runner, cwd=cwd, repo=repo)

        cmd = ['git', '--work-tree=.', 'submodule', 'update']
        if init:
            cmd.append('--init')

        # TODO: --recursive would need us to update/create ItemRepos recursively
        # and return created items. It's not just adding the option!

        super(ItemUpdateSubmodules, self).__init__(
            cmd=cmd, runner=runner, item=None, cwd=cwd, repo=repo,
            check_definition=check_definition
        )
        self._init = init

    def _check_definition(self, init, runner, cwd, repo):
        log("Processing definition of %s", self.__class__)
        # ATM nothing to do

    def create(self):
        log("Executing %s in %s", self.__class__, self.path)

        # Note, that we couldn't discover submodules to be updated/init'ed
        # during instantiation (thus self._ref_item is empty).
        # self._repo.create() may have created them since.
        # Therefore, let's get them now and include them explicitly in the call
        self._ref_items = [sm for sm in self._repo.submodules]

        # If there are none, we have nothing to do
        if not self._ref_items:
            log("Found no submodules in %s(%s).", self._repo, self._repo.path)
            return

        self._cmd.append('--')
        # Note, this might be wrong if there's heavy use of runner/cwd option!
        self._cmd.extend([os.path.relpath(sm.path, self._repo.path)
                          for sm in self._ref_items])

        # run the command:
        super(ItemUpdateSubmodules, self).create()

        new_items = set()
        if self._init:
            # we possibly init'ed submodules
            # => ItemRepo instances need to be updated
            for sm in self._ref_items:
                if not sm._is_initialized:
                    # wasn't initialized before, is now
                    sm._is_initialized = True
                    new_items.update(sm._update_from_src())
                    if sm.is_annex and sm._annex_init:
                        sm._call_annex_init()

        return new_items


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

