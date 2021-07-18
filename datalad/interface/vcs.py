import logging
import datalad.utils as ut
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.core.local.repo import repo_from_path
# DueCredit
from datalad.support.due import due
from datalad.support.due_utils import duecredit_dataset
# Flyweight
from datalad.dataset.repo import (
    path_based_str_repr,
    PathBasedFlyweight,
)
from weakref import WeakValueDictionary
from datalad.dochelpers import borrowdoc

lgr = logging.getLogger('datalad.vcs')


@path_based_str_repr
class VCS(object, metaclass=PathBasedFlyweight):
    """Highest abstraction layer to promise deprecation cycles for its public attributes"""

    # Begin Flyweight
    _unique_instances = WeakValueDictionary()

    def _flyweight_invalid(self):
        """Invalidation of Flyweight instance

        Doesn't need to be invalidated during its lifetime at all. Instead the
        underlying *Repo instances are. Can represent a not yet existing path.

        This is the same behavior as `Dataset`. Might need to change if/when
        validation of `self._repository` is reworked.
        """
        return False

    def __hash__(self):
        # TODO: This can probably be moved to (and inherited from)
        #       PathBasedFlyweight.
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    # End Flyweight

    def __init__(self, path):

        if isinstance(path, ut.Path):
            self.pathobj = path
            self.path = str(path)
        else:
            self.pathobj = ut.Path(path)
            self.path = path
        self._repo = None

    @property
    def _repository(self):
        """Get an instance of the version control system/repo for this dataset,
        or None if there is none yet (or none anymore).

        If testing the validity of an instance of GitRepo is guaranteed to be
        really cheap this could also serve as a test whether a repo is present.

        Note, that this property is evaluated every time it is used. If used
        multiple times within a function it's probably a good idea to store its
        value in a local variable and use this variable instead.

        Returns
        -------
        GitRepo or AnnexRepo
        """

        # If we already got a *Repo instance, check whether it's still valid;
        # Note, that this basically does part of the testing that would
        # (implicitly) be done in the loop below again. So, there's still
        # potential to speed up when we actually need to get a new instance
        # (or none). But it's still faster for the vast majority of cases.
        #
        # TODO: Dig deeper into it and melt with new instance guessing. This
        # should also involve to reduce redundancy of testing such things from
        # within Flyweight.__call__, AnnexRepo.__init__ and GitRepo.__init__!
        #
        # Also note, that this could be forged into a single big condition, but
        # that is hard to read and we should be well aware of the actual
        # criteria here:
        if self._repo is not None and self.pathobj.resolve() == self._repo.pathobj:
            # we got a repo and path references still match
            if isinstance(self._repo, AnnexRepo):
                # it's supposed to be an annex
                # Here we do the same validation that Flyweight would do beforehand if there was a call to AnnexRepo()
                if self._repo is AnnexRepo._unique_instances.get(
                        self._repo.path,
                        None) and not self._repo._flyweight_invalid():
                    # it's still the object registered as flyweight and it's a
                    # valid annex repo
                    return self._repo
            elif isinstance(self._repo, GitRepo):
                # it's supposed to be a plain git
                # same kind of checks as for AnnexRepo above, but additionally check whether it was changed to have an
                # annex now.
                # TODO: Instead of is_with_annex, we might want the cheaper check for an actually initialized annex.
                #       However, that's not completely clear. On the one hand, if it really changed to be an annex
                #       it seems likely that this happened locally and it would also be an initialized annex. On the
                #       other hand, we could have added (and fetched) a remote with an annex, which would turn it into
                #       our current notion of an uninitialized annex. Question is whether or not such a change really
                #       need to be detected. For now stay on the safe side and detect it.
                if self._repo is GitRepo._unique_instances.get(
                        self._repo.path,
                        None) and not self._repo._flyweight_invalid() and not \
                        self._repo.is_with_annex():
                    # it's still the object registered as flyweight, it's a
                    # valid git repo and it hasn't turned into an annex
                    return self._repo

        # Note: Although it looks like the "self._repo = None" assignments
        # could be used instead of variable "valid", that's a big difference!
        # The *Repo instances are flyweights, not singletons. self._repo might
        # be the last reference, which would lead to those objects being
        # destroyed and therefore the constructor call would result in an
        # actually new instance. This is unnecessarily costly.
        try:
            self._repo = repo_from_path(self.path)
        except ValueError:
            lgr.log(5, "Failed to detect a valid repo at %s", self.path)
            self._repo = None
            return

        if due.active:
            # TODO: Figure out, when exactly this is needed. Don't think it
            #       makes sense to do this for every dataset,
            #       no matter what => we want .repo to be as cheap as it gets.
            # Makes sense only on installed dataset - @never_fail'ed
            duecredit_dataset(self)

        return self._repo

    def close(self):
        """Perform operations which would close any possibly attached processes
        """
        repo = self._repo
        self._repo = None
        if repo:
            # might take care about lingering batched processes etc
            del repo

    @borrowdoc(GitRepo)
    def call_git(self, args, files=None, expect_stderr=False, expect_fail=False,
                 read_only=False):

        return self._repository.call_git(args, files=None, expect_stderr=False,
                                         expect_fail=False, read_only=False)

    @borrowdoc(GitRepo)
    def call_git_items_(self, args, files=None, expect_stderr=False, sep=None,
                        read_only=False):
        return self._repository.call_git_items_(args, files=None,
                                                expect_stderr=False,
                                                sep=None, read_only=False)

    @borrowdoc(GitRepo)
    def call_git_oneline(self, args, files=None, expect_stderr=False,
                         read_only=False):
        return self._repository.call_git_oneline(args, files=None,
                                                 expect_stderr=False,
                                                 read_only=False)

    @borrowdoc(GitRepo)
    def call_git_success(self, args, files=None, expect_stderr=False,
                         read_only=False):
        return self._repository.call_git_success(args, files=None,
                                                 expect_stderr=False,
                                                 read_only=False)

    @borrowdoc(AnnexRepo)
    def call_annex_records(self, args, files=None):

        return self._repository.call_annex_records(args, files=None)

    @borrowdoc(AnnexRepo)
    def call_annex(self, args, files=None):

        return self._repository.call_annex(args, files=None)

    @borrowdoc(AnnexRepo)
    def call_annex_items_(self, args, files=None, sep=None):

        return self._repository.call_annex_items_(args, files=None, sep=None)

    @borrowdoc(AnnexRepo)
    def call_annex_oneline(self, args, files=None):

        return self._repository.call_annex_oneline(args, files=None)
