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


#
# TODO: From respective github-issue:
#
#     ATM create_sibling has custom code to perform a bunch of operations via
#     SSH that are equivalents of:
#
#     exist()
#     rmtree()
#     chmod
#     chgrp
#     rm
#     mkdir()
#     git update-server-info
#     git config
#     enable post-update hook
#     annex init
#


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

    def make_directory(self, path, force=False):
        path = self._ensure_absolute_remote(path)
        self.con("mkdir {} {}".format("-p" if force else "",
                                      quote_cmdlinearg(str(path))))

    def exists(self, path):
        path = self._ensure_absolute_remote(path)
        try:
            self.con("test -e {}".format(quote_cmdlinearg(str(path))))
            return True
        except CommandError:
            return False

    def remove(self, path, recursive=False):
        path = self._ensure_absolute_remote(path)
        path = quote_cmdlinearg(str(path))

        # test for directory:
        isdir = True
        try:
            self.con('[ -d {} ]'.format(path))
        except CommandError as e:
            if e.code != 0:
                isdir = False

        # build actual command
        if isdir:
            if recursive:
                cmd = "rm -r -f {}".format(path)
            else:
                cmd = "rmdir {}".format(path)

        else:
            cmd = "rm -f {}".format(path)

        self.con(cmd)

    def rename(self, src, dst):
        src = self._ensure_absolute_remote(src)
        dst = self._ensure_absolute_remote(dst)

        self.con('mv {} {}'.format(quote_cmdlinearg(str(src)),
                                   quote_cmdlinearg(str(dst))))

    def change_permissions(self, path, mode, recursive=False):
        path = self._ensure_absolute_remote(path)

        self.con("chmod {} {} {}".format(
            mode,
            "-R" if recursive else "",
            quote_cmdlinearg(str(path))
        ))

    def change_group(self, path, label, recursive=False):
        path = self._ensure_absolute_remote(path)

        self.con("chgrp {} {} {}".format(
            "-R" if recursive else "",
            label,
            quote_cmdlinearg(str(path))
        ))


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
