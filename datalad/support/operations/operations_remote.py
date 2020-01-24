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
from datalad.support.exceptions import CommandError
from datalad.utils import (
    Path,
    PurePath
)
from datalad.cmd import Runner
from datalad.utils import (
    quote_cmdlinearg,
    on_windows,
)

# TODO: We actually need to add/overwrite quote_cmdlinearg/on_windows funtions
#       to sense what's going on at the remote end. However, this requires a
#       test setup where local+remote are different indeed. Note, that this
#       would include to not resolve Path objects locally (prob. allow for
#       PurePath only when addressing remote locations?).

# TODO: What about Windows Servers? Does SSH give a POSIX Shell? Might need a
#       dedicated class


class RemoteSSHShellOperations(RemoteOperationsBase):

    def __init__(self, url,
                 cwd=None,
                 remote_cwd=None,
                 use_remote_annex_bundle=True,
                 force_ip=False):

        super().__init__(cwd, remote_cwd)
        from datalad import ssh_manager

        self.con = ssh_manager.get_connection(
            url=url,
            use_remote_annex_bundle=use_remote_annex_bundle,
            force_ip=force_ip)

        # TODO: Not sure yet about the following part. Might be better to
        #   to deal with this per command
        self.con.open()
        if self._remote_cwd:
            self.con("cd {}".format(quote_cmdlinearg(str(self._remote_cwd))))

    def make_directory(self, path, force=False):
        self.con("mkdir {} {}".format("-p" if force else "",
                                      quote_cmdlinearg(str(path))))

    def exists(self, path):
        try:
            self.con("test -e {}".format(quote_cmdlinearg(str(path))))
            return True
        except CommandError:
            return False

    def remove(self, path, recursive=False):

        self.con('rm {} -f {}'.format('-r' if recursive else '',
                                      quote_cmdlinearg(str(path))))

    def rename(self, src, dst):

        self.con('mv {} {}'.format(quote_cmdlinearg(str(src)),
                                   quote_cmdlinearg(str(dst))))


class RemotePersistentSSHShellOperations(RemoteOperationsBase):

    # TODO: see RIA special remote. Instead of single shh execution stream
    #  everything through a persistent remote shell

    pass


# TODO: in operations_local we integrate decision on what to use in import of
#       `LocalOperation`. What criterion would we use here to decide what
#       class to use?
#       -> decision may well be based on "URL-scheme" including ones like
#       "ria+ssh"
RemoteOperation = RemoteSSHShellOperations
