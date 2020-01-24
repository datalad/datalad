# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""
from datalad.support.operations.operations_abstract import RemoteOperationsBase
from datalad.cmd import Runner
from datalad.utils import (
    quote_cmdlinearg,
    on_windows,
)


# TODO: What about Windows Servers? Does SSH give a POSIX Shell? Might need a
#       dedicated class
# TODO: in operations_local we integrate decision on what to use in import of
#       `LocalOperation`. What criterion would we use here to decide what
#       class to use?

class RemoteSSHShellOperations(RemoteOperationsBase):

    def __init__(self, cwd=None, remote_cwd=None):
        super().__init__(cwd, remote_cwd)

        from datalad import ssh_manager

        # TODO: For now basically use existing ssh execution


class RemotePersistentSSHShellOperations(RemoteOperationsBase):

    # TODO: see RIA special remote. Instead of single shh execution stream
    #  everything through a persistent remote shell

    pass
