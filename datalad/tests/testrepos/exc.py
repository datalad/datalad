# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Exceptions for test repositories
"""
from os import linesep


class TestRepoError(Exception):
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
        super(TestRepoError, self).__init__(msg)
        self.repo = repo
        self.item = item
        self.index = index

    def __str__(self):
        to_str = ""
        to_str += " in {}".format(self.repo) if self.repo else ""
        to_str += " at index {}".format(self.index) if self.index else ""
        to_str += " for item {}.".format(self.item) if self.item else "."
        to_str += linesep
        return to_str + (self.message if self.message else "")


class InvalidTestRepoDefinitionError(TestRepoError):
    """Thrown if the definition of a test repository is invalid
    """

    def __str__(self):
        return "Invalid definition" + \
               super(InvalidTestRepoDefinitionError, self).__str__()


class TestRepoCreationError(TestRepoError):
    """Thrown if the creation of a test repository failed
    """

    def __str__(self):
        return "Creation failed" + \
               super(TestRepoCreationError, self).__str__()


class TestRepoAssertionError(TestRepoError):
    """Thrown if assert_* methods of testrepos.items or testrepos.repos
    encountered an error"""

    def __str__(self):
        return "Assertion failed" + \
               super(TestRepoAssertionError, self).__str__()