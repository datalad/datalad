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

import logging
import os

from abc import ABCMeta, abstractmethod
from os.path import join as opj
from collections import OrderedDict


from six import add_metaclass

from datalad.cmd import GitRunner
from datalad.support.network import get_local_file_url

from datalad.tests.testrepos.exc import InvalidTestRepoDefinitionError, \
    TestRepoCreationError, TestRepoError
from datalad.tests.testrepos.items import Item, ItemRepo, ItemSelf, ItemFile, \
    ItemInfoFile, ItemCommand, ItemCommit, ItemDropFile, ItemAddSubmodule, ItemUpdateSubmodules
from datalad.tests.utils import eq_, assert_is_instance, assert_in

from datalad.utils import assure_list
from datalad.utils import auto_repr
from datalad.dochelpers import exc_str
import tempfile
from .. import _TEMP_PATHS_GENERATED
from ..utils import get_tempfile_kwargs
import os



lgr = logging.getLogger('datalad.tests.testrepos.repos')


def log(*args, **kwargs):
    """helper to log at a default level

    since this is not even about actual datalad tests, not to speak of actual
    datalad code, log at pretty low level.
    """
    lgr.log(5, *args, **kwargs)


@auto_repr
@add_metaclass(ABCMeta)
class TestRepo_NEW(object):  # object <=> ItemRepo?
    """Base class for test repositories
    """

    # version of that test repository; might be used to determine a needed
    # update if used persistently
    version = '0.1'  # TODO: version for abstract class? May be none at all

    # old name to be used by a transition decorator to ease RF'ing
    RF_str = None
    # definition to be done by subclasses
    _cls_item_definitions = []
    # list of tuples: Item's class and kwargs for constructor
    # Note:
    # - item references are paths
    # - 'path' and 'cwd' arguments are relative to TestRepo's root
    # TODO: a lot of doc

    def __init__(self, path, runner=None):
        """

        Parameters
        ----------
        path: str
            absolute path of the location to create this instance at
        runner: Runner or None
        """

        # RF: to have a function specifying that a certain kwarg needs
        # to be an Item from path. Accept actual Items as well.
        # What are the requirements for those items in terms of being known to
        # TestRepo?

        # include src in the list of things, that have to be an item
        # exception? We don't need to know anything about an annex-addurl'ed file except it's path and may be contetn.
        # If it's going to be an ItemFile, it does not have a repo!






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
                    except KeyError as e:
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
        self._items = OrderedDict()
        self._execution = []

        # Make sure we operate on a copy per instance, since we manipulate the
        # definitions on a per instance basis (paths for example)!
        from copy import deepcopy
        self._item_definitions = deepcopy(self._cls_item_definitions)

        # Make sure, we have a definition:
        if not self._item_definitions:
            raise InvalidTestRepoDefinitionError(
                msg="Found no definition at all.",
                repo=self.__class__
            )

        log("Processing definition of %s(%s)", self.__class__, path)
        for item, index in zip(self._item_definitions,
                               range(len(self._item_definitions))):

            # special case: Another subclass of TestRepo
            if issubclass(item[0], TestRepo_NEW):
                # TODO: pass runner?

                # can't be another instance of what we are currently defining:
                if item[0] == self.__class__:
                    raise InvalidTestRepoDefinitionError(
                        msg="Can't use {cls} within its own definition:{ls}"
                            "{cl}({args})".format(ls=os.linesep,
                                                  cl=item[0].__name__,
                                                  args=item[1]
                                                  ),
                        repo=self.__class__,
                        item=item[0].__name__,
                        index=index
                        )

                # 1. do the path conversion
                # Note, that 'item' is another TestRepo. It's 'path' argument
                # needs to be absolute and we currently are within the
                # definition of a TestRepo using it as an "item". Therefore
                # paths are relative to self.path here.
                r_path = item[1].get('path', None)
                if not r_path:
                    raise InvalidTestRepoDefinitionError(
                        msg="Missing argument 'path' for {cl}:{ls}"
                            "{cl}({args})".format(ls=os.linesep,
                                                  cl=item[0].__name__,
                                                  args=item[1]),
                        repo=self.__class__,
                        item=item[0].__name__,
                        index=index
                        )

                item[1]['path'] = os.path.normpath(opj(self._path, r_path))
                # 2. instantiate it:
                try:
                    testrepo = item[0](**item[1])
                except InvalidTestRepoDefinitionError as e:
                    # add information the item's class can't know:
                    e.repo = self.__class__
                    e.index = index
                    raise e

                # 3. deal with ItemSelf
                # if r_path was '.', we simply inherit ItemSelf - no need to
                # change anything, it will be included automatically when
                # getting the sub's items. Otherwise we need to replace ItemSelf
                # in the sub's definition by an ItemRepo.
                if r_path != '.':
                    item_self = testrepo.repo
                    assert_is_instance(item_self, ItemSelf)

                    # Note: Replacement requirements include all references to
                    # that ItemSelf!
                    # just hack the object, so it's not considered to be an
                    # ItemSelf by isinstance anymore (note, that ItemSelf
                    # actually is just an ItemRepo with a different class name):
                    item_self.__class__ = ItemRepo
                else:
                    self.repo = testrepo.repo

                # 4. get its items, add them here using corrected relative path
                # and be done

                # Note, that we do NOT include those items in our execution
                # list, since they were created already by instantiation of the
                # sub TestRepo!
                for sub_it in testrepo._items:
                    sub_r_path = os.path.relpath(testrepo._items[sub_it].path,
                                                 self._path)
                    self._items[sub_r_path] = testrepo._items[sub_it]
                continue

            if not (issubclass(item[0], Item) and isinstance(item[1], dict)):
                raise InvalidTestRepoDefinitionError(
                    msg="Malformed definition entry. An entry of a TestRepo's "
                        "definition list is expected to be a tuple, consisting "
                        "of a subclass of Item and a dict, containing kwargs "
                        "for its instantiation. Entry at index {idx} is "
                        "violating this constraint:{ls}{cl}({args})"
                        "".format(ls=os.linesep,
                                  cl=item[0],
                                  args=item[1],
                                  idx=index
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

            # check and convert 'repo' argument for files
            # TODO: We already have that (kind of) for ItemCommand. May be melt
            # in. Definitely do it, if we are to provide this also for ItemRepo
            # as an option to instantly submodule-add
            if issubclass(item[0], ItemFile):
                r_repo = item[1].get('repo')
                if not r_repo:
                    raise InvalidTestRepoDefinitionError(
                        msg="Missing argument 'repo' for {cl}:{ls}"
                            "{cl}({args})".format(s=os.linesep,
                                                  cl=item[0].__name__,
                                                  args=item[1]),
                            repo=self.__class__,
                            item=item[0].__name__,
                            index=index
                            )
                # convert to ItemRepo:
                _path2item(item, index, 'repo')

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

        # Now, actually create the beast physically:
        log("Physically creating %s", self.__class__)
        self.create()

        # There might be ItemRepo(s) besides the top-level one, that were never
        # added as a submodule to another one. For recursive calls of
        # assert_intact, we need all roots of this forrest. Furthermore, even
        # ItemSelf might not be a root.
        # We can discover them only now after all Items were created, since
        # ItemCommands may have changed what could have been discovered during
        # instantiation.
        self._roots = {self._items[p] for p in self._items
                       if isinstance(self._items[p], ItemRepo) and
                       self._items[p].superproject is None}

        # Note, that by now there's no limitation on whether or not there needs
        # to be an item '.'. Theoretically everything should work with several
        # hierarchies in parallel, self.path being their common root location.
        # However, if there is an item '.', it must not be an ItemFile. If so,
        # something went wrong.
        if self._items.get('.') and isinstance(self._items['.'], ItemFile):
            raise InvalidTestRepoDefinitionError(
                msg="Item at root location {p} must not be a file: {cl}('.')"
                    "".format(cl=self._items['.'].__class__,
                              p=self.path),
                item=self._items['.']
            )

        # We are all done. Check it:
        log("Check integrity of %s", self.__class__)
        self.assert_intact()

    # properties pointing to ItemSelf (self.repo)!
    @property
    def path(self):
        return self.repo.path

    @property
    def url(self):
        return self.repo.url

    def assert_intact(self):
        """Assertions to run to check integrity of this test repository

        Should probably be enhanced by subclasses and is supposed to recursively
        call assert_intact of its items. Therefore, call it via super if you
        derive a new class!
        """

        log("Default integrity check by %s for %s", TestRepo_NEW, self.__class__)
        # object consistency:

        assert_is_instance(self.repo, ItemSelf)
        [assert_is_instance(it, ItemRepo) for it in self._roots]
        [assert_is_instance(self._items[p], Item) for p in self._items]

        # everything, that's in the definition, needs to be in the execution
        # list
        # TODO: come up with a better idea than just testing length. Note, that
        # execution can't be a dict and definition does not contain actual
        # instances
        # Note: The original assumption isn't actually true anymore, since we
        # allow for other TestRepos to be sucked in. Those create based on their
        # own execution list, so we don't enhance our execution list but have
        # those TestRepos in our definition
        # Therefore: Don't know yet, what to assert instead - outcommenting
        # for now:
        #eq_(len(self._item_definitions), len(self._execution))
        #eq_(set(self._items[p] for p in self._items),
        #    set(it for it in self._execution if not isinstance(it, ItemCommand)))

        # all items are recursively accessible via self._roots:
        def get_items_recursively(item):
            # everything directly underneath
            items = item._items
            result = set(items)
            # plus recursively all subrepos
            for it in items:
                if isinstance(it, ItemRepo):
                    result = result.union(get_items_recursively(it))

            return result

        reachable = self._roots
        for it in self._roots:
            reachable = reachable.union(get_items_recursively(it))
        eq_(reachable, set(self._items[p] for p in self._items))

        # check them recursively:
        [item.assert_intact() for item in self._roots]

        # TODO: Is there more we can test by default at this level?

    def create(self):
        """Physically create the beast
        """
        log("Default creation routine by %s for %s", TestRepo_NEW, self.__class__)

        # default implementation:
        for item, index in zip(self._execution, range(len(self._execution))):
            try:
                new_items = item.create()
            except TestRepoCreationError as e:
                # add information the Item classes can't know:
                e.repo = self.__class__
                e.index = index
                raise e
            if new_items:
                for it in new_items:
                    r_path = os.path.relpath(it.path, self.path)
                    if r_path in self._items:
                        if it is not self._items[r_path]:
                            # we already got sth at this location and it's not
                            # the same thing
                            raise TestRepoCreationError(
                                msg="While creating {it}({p}) received new item "
                                    "{new}({p_new}), but already got something at "
                                    "this location and it's not the same object "
                                    "({old})".format(it=item,
                                                     p=item.path,
                                                     new=it,
                                                     p_new=it.path,
                                                     old=self._items[r_path]),
                                item=item.__class__,
                                repo=self.__class__,
                                index=index
                            )
                        else:
                            # we know it already for some reason
                            continue
                    else:
                        self._items[r_path] = it

#
# Definition of persistent files to be used by TestRepo's subclasses for
# annex-addurl'ing stuff
#

# To be enhanced if needed. See BasicMixed testrepo for an example on how it
# is used.
# Each file is a tuple of a content str and a path. The paths are relative to
# the _persistent_store_root
remote_file_list = [('test-annex.dat', "content to be annex-addurl'd")]


#
# Tools for getting and lazily creating persistent files and TestRepos
#

# Note: Would be nice to have that in a different file, but ATM I don't see
# another way to avoid circular import yet, since TestRepo's subclasses need to
# access persistent locations to annex-addurl/clone from.


def _make_persistent_store():
    """Creates a store for files and TestRepo instances, that are persistent
    across tests

    create a temp directory, where to store files and repos persistently
    across tests; this is needed for files, that should be annex-addurl'd by
    definition of a TestRepo for example and for persistent TestRepos.

    Additionally, have


    """
    # TODO: We might want to be able to configure a non-temporary location for
    # this store to be persistent even across test runs

    # TODO: prefix='testrepo': Somehow failed when prefix was changed. Need to
    # dig into it at some point.
    path = tempfile.mkdtemp(**get_tempfile_kwargs({}, prefix='testrepo_store'))
    _TEMP_PATHS_GENERATED.append(path)
    # subdirs for files and testrepos
    os.makedirs(opj(path, 'files'))
    os.makedirs(opj(path, 'testrepos'))
    return path

_persistent_store_root = _make_persistent_store()
_persistent_repo_store = dict()


def get_persistent_file(path):
    """Get the actual (temp) path to a file, defined by `path` in
    `remote_file_list`

    Creates that file if it wasn't created yet.
    """

    entry = [f for f in remote_file_list if f[0] == path]
    if len(entry) == 0:
        raise InvalidTestRepoDefinitionError(
            msg="Persistent file {p} referenced but not found in "
                "remote_file_list".format(p=path))
    if len(entry) != 1:
        raise InvalidTestRepoDefinitionError(
            msg="Ambiguous definition of persisten file {p}".format(p=path)
        )
    entry = entry[0]
    real_path = opj(_persistent_store_root, 'files', path)
    if not os.path.exists(real_path):
        # check for possible subdirs to make:
        dir_ = os.path.dirname(real_path)
        if not os.path.exists(dir_):
            os.makedirs(dir_)
        with open(real_path, "w") as f:
            f.write(entry[1])

    return real_path


def get_persistent_testrepo(cls, attr=None):
    """Get persistent instance of `cls`

    Creates that TestRepo if required and checks its integrity via assert_intact
    before delivering
    """

    if not issubclass(cls, TestRepo_NEW):
        raise InvalidTestRepoDefinitionError(
            msg="{cl} is not a subclass of TestRepo".format(cl=cls)
        )

    # Note: instead of lower() we might want to base the path on
    # CamelCase conversion like camel_case
    path = opj(_persistent_store_root, 'testrepos', cls.__name__.lower())

    def lazy_delivery():
        if cls.__name__ not in _persistent_repo_store:
            _persistent_repo_store[cls.__name__] = cls(path=path)
        else:
            try:
                _persistent_repo_store[cls.__name__].assert_intact()
            except (TestRepoError, AssertionError) as e:
                lgr.debug("Persistent TestRepo '{c}' damaged ({exc}). "
                          "Recreating.".format(c=cls.__name__,
                                               exc=exc_str(e)))
                from datalad.utils import rmtree
                rmtree(path)
                _persistent_repo_store[cls.__name__] = cls(path=path)

        if attr is None:
            return _persistent_repo_store[cls.__name__]
        else:
            return getattr(_persistent_repo_store[cls.__name__], attr)

    return lazy_delivery
# apparently required to make nose not try to run it:
get_persistent_testrepo.__test__ = False


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

    # old name to be used by a transition decorator to ease RF'ing
    RF_str = 'basic_git'

    _cls_item_definitions = [
        (ItemSelf, {'path': '.',
                    'annex': False}),
        (ItemInfoFile, {'state': (ItemFile.ADDED,
                                  ItemFile.UNMODIFIED),
                        'repo': '.'}),
        (ItemFile, {'path': 'test.dat',
                    'content': "123",
                    'annexed': False,
                    'state': (ItemFile.ADDED,
                              ItemFile.UNMODIFIED),
                    'repo': '.'}),

        (ItemCommit, {'cwd': '.',
                      'item': ['test.dat', 'INFO.txt'],
                      'msg': "Adding a basic INFO file and "
                             "rudimentary load file."})
    ]


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

    # old name to be used by a transition decorator to ease RF'ing
    RF_str = 'basic_annex'

    _cls_item_definitions = [
        (ItemSelf, {'path': '.',
                    'annex': True}),
        (ItemInfoFile, {'state': (ItemFile.ADDED,
                                  ItemFile.UNMODIFIED),
                        'repo': '.'}),
        (ItemFile, {'path': 'test.dat',
                    'content': "123",
                    'annexed': False,
                    'state': (ItemFile.ADDED,
                              ItemFile.UNMODIFIED),
                    'repo': '.'}),
        (ItemCommit, {'cwd': '.',
                      'item': ['test.dat', 'INFO.txt'],
                      'msg': "Adding a basic INFO file and "
                             "rudimentary load file for annex "
                             "testing"}),
        (ItemFile, {'path': 'test-annex.dat',
                    'src': get_local_file_url(get_persistent_file('test-annex.dat')),
                    'state': (ItemFile.ADDED,
                              ItemFile.UNMODIFIED),
                    'annexed': True,
                    'key': "SHA256E-s28--2795fb26981c5a687b9bf44930cc220029223f472cea0f0b17274f4473181e7b.dat",
                    'repo': '.'
                    }),
        (ItemCommit, {'cwd': '.',
                      'item': 'test-annex.dat',
                      'msg': "Adding a rudimentary git-annex load file"}),
        (ItemDropFile, {'cwd': '.',
                        'item': 'test-annex.dat'})
    ]


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


# TODO: Do not request actual instances in definition! Just paths.

class MixedSubmodulesOldOneLevel(TestRepo_NEW):
    """Hierarchy of repositories with files in git and in annex

    It consists of three instances of BasicMixed (one at top-level and two as
    direct submodules) and does so to resemble the old `SubmoduleDataset`.

    RF'ing note: This resembles the old `SubmoduleDataset`. The only difference
    is the content of INFO.txt, which is now more detailed. In particular it
    includes the entire definition of this test repository. Whenever tests are
    rewritten to not explicitly rely on this one, it might go in favor of a more
    general one.
    """

    # TODO: Actually, it's still not entirely the same as before, since we add
    # those submodules inplace, instead of having them cloned via submodule-add
    # and then initialized. Checkout whether this makes a difference in the
    # setup (if anything it's about .git probably)

    version = '0.1'

    # old name to be used by a transition decorator to ease RF'ing
    RF_str = 'submodule_annex'

    # Note, that we can simply extend the definition list of BasicMixed here:
    _cls_item_definitions = BasicMixed._cls_item_definitions + \
        [
            # Here we specify a clone of a persistent instance of BasicMixed:
            (ItemRepo, {'path': 'subm 1',
                        'src': get_persistent_testrepo(BasicMixed, 'repo'),
                        'annex': True,
                        'annex_init': True}),
            (ItemRepo, {'path': '2',
                        'src': get_persistent_testrepo(BasicMixed, 'repo'),
                        'annex': True,
                        'annex_init': True}),
            # Add both ItemRepos as submodules and commit:
            (ItemAddSubmodule, {'cwd': '.',
                                'repo': '.',
                                'item': ['subm 1', '2'],
                                'commit': True,
                                'commit_msg': "Added subm 1 and 2."}),
        ]


class MixedSubmodulesOldNested(TestRepo_NEW):
    """Hierarchy of repositories with files in git and in annex

    It consists of three instances of MixedSubmodulesOldOneLevel (one at
    top-level and one as its submodule and another one as a submodule of the
    second one) and does so to resemble the old `NestedDataset`.

    RF'ing note: This resembles the old `NestedDataset`. The only difference
    is the content of INFO.txt, which is now more detailed. In particular it
    includes the entire definition of this test repository. Whenever tests are
    rewritten to not explicitly rely on this one, it might go in favor of a more
    general one.
    """

    version = '0.1'

    # old name to be used by a transition decorator to ease RF'ing
    RF_str = 'nested_submodule_annex'

    _cls_item_definitions = [
        # Use BasicMix as an item in that list just for demo:
        # it's effect is the same as extending BasicMixed._cls_item_definition
        # as it's done in MixedSubmodulesOldOneLevel above:
        (BasicMixed, {'path': '.'}),

        # get a clone of MixedSubmodulesOldOneLevel:
        (ItemRepo, {'path': 'sub dataset1',
                    'src': get_persistent_testrepo(MixedSubmodulesOldOneLevel, 'repo'),
                    'annex': True,
                    'annex_init': True}),
        (ItemUpdateSubmodules, {'repo': 'sub dataset1',
                                'init': True}),
        # Now, one level deeper:
        (ItemRepo, {'path': opj('sub dataset1', 'sub sub dataset1'),
                    'src': get_persistent_testrepo(MixedSubmodulesOldOneLevel, 'repo'),
                    'annex': True,
                    'annex_init': True}),
        (ItemUpdateSubmodules, {'repo': opj('sub dataset1', 'sub sub dataset1'),
                                'init': True}),
        (ItemAddSubmodule, {'cwd': 'sub dataset1',
                            'repo': 'sub dataset1',
                            'item': opj('sub dataset1', 'sub sub dataset1'),
                            'commit': True,
                            'commit_msg': "Added sub dataset"}),
        # And add/commit the entire subtree:
        (ItemAddSubmodule, {'cwd': '.',
                            'repo': '.',
                            'item': 'sub dataset1',
                            'commit': True,
                            'commit_msg': "Added subdatasets."}),
        #(ItemCommand, {''})#cmd, runner=None, item=None, cwd=None, repo=None



    ]

# Datasets (.datalad/config, .datalad/metadata ...) ?
