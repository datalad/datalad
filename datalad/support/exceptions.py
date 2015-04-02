# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" datalad exceptions
"""


class AnnexCommandError(Exception):

    def __init__(self, cmd="", msg="", code=None):
        self.cmd = cmd
        self.msg = msg
        self.code = code

    def __str__(self):
        to_str = "%s: command '%s'" % (self.__class__.__name__, self.cmd)
        if self.code:
            to_str += " failed with exitcode %d" % self.code
        to_str += ".\n%s" % self.msg
        return to_str


class AnnexCommandNotAvailableError(AnnexCommandError):
    pass


class AnnexFileNotInAnnexError(AnnexCommandError, IOError):

    def __init__(self, cmd="", msg="", code=None, filename=""):
        AnnexCommandError.__init__(self, cmd=cmd, msg=msg, code=code)
        IOError.__init__(self, code, "%s: %s" % (cmd, msg), filename)

    def __str__(self):
        return "%s\n%s" % (AnnexCommandError.__str__(self), IOError.__str__(self))


class AnnexFileInGitError(AnnexFileNotInAnnexError):
    pass