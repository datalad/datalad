# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to a ssh connection.

Allows for connecting via ssh and keeping the connection open
(by using a controlmaster), in order to perform several ssh commands or
git calls to a ssh remote without the need to reauthenticate.
"""

import logging
from os import geteuid  # Linux specific import
from subprocess import Popen
from shlex import split as sh_split

from six.moves.urllib.parse import urlparse

from datalad.support.gitrepo import GitRepo
from datalad.utils import not_supported_on_windows
from datalad.utils import on_windows
from datalad.utils import assure_dir
from datalad.utils import auto_repr
from datalad.cmd import Runner
from datalad.support.exceptions import CommandError

lgr = logging.getLogger('datalad.ssh')


@auto_repr
class SSHConnector(object):
    """Representation of a ssh connection.
    """

    def __init__(self, url=None, repo=None):
        not_supported_on_windows("TODO: Make SSHConnector an abstraction to "
                                 "interface platform dependent SSH")
        self.runner = Runner()
        self.host = None
        self.ctrl_master = None
        self.pwd = None

        if url:
            self.open(url)
        if repo:
            self.use_with_repo(repo)

    def open(self, url=None, dir_=None):
        """

        Parameters
        ----------
        url: str
          URL to connect to
        dir_:
          set remote working directory
        """
        # TODO: What if already connected? Close and open (url) or just fail?

        # parse url:
        parsed_target = urlparse(url)
        if parsed_target.scheme != 'ssh':
            raise ValueError("Not an SSH URL: %s" % url)
        self.host = parsed_target.netloc
        if not self.host:
            raise ValueError("Malformed URL (missing host): %s" % url)
        if dir_ is None:
            self.pwd = parsed_target.path # TODO: Needed here? if parsed_target.path else '.'

        # setup SSH Connection:
        # - build control master:
        socket_dir = "/var/run/user/%s/datalad" % geteuid()
        assure_dir(socket_dir)
        self.ctrl_master = "%s/%s" % (socket_dir, self.host)
        if parsed_target.port:
            self.ctrl_master += ":%s" % parsed_target.port

        # - start control master:
        cmd = "ssh -o ControlMaster=yes -o \"ControlPath=%s\" " \
              "-o ControlPersist=yes %s exit" % (self.ctrl_master, self.host)
        lgr.debug("Try starting control master by calling:\n%s" % cmd)
        proc = Popen(cmd, shell=True)
        proc.communicate(input="\n")  # why the f.. this is necessary?

        # TODO: 'force' to create it?
        if self.pwd:
            try:
                self.run_on_remote(['ls', self.pwd])
            except CommandError as e:
                if "No such file or directory" in e.stderr \
                        and self.pwd in e.stderr:

                    raise ValueError("%s doesn't exist on remote.")

                raise  # unexpected error

            self.run_on_remote(['cd', self.pwd])

    def close(self):
        # stop controlmaster:
        cmd = ["ssh", "-O", "stop", "-S", self.ctrl_master, self.host]
        self.runner.run(cmd, expect_stderr=True)

    def use_with_repo(self, repo=None):
        """Let git use this connection for `repo`

        Parameters
        ----------
        repo: GitRepo

        """
        if not isinstance(repo, GitRepo):
            raise ValueError("Don't know how to handle repo of type '%s'" %
                             type(repo))
        from pkg_resources import resource_filename
        repo.cmd_call_wrapper.env["GIT_SSH"] = \
            resource_filename('datalad', 'resources/git_ssh.sh')

        # TODO: How to deal with gitpython?
        # TODO: Maybe make it a method of GitRepo instead (GitRepo.use_ssh)

    def run_on_remote(self, cmd):
        """

        Parameters
        ----------
        cmd: list or str
          command to run on the remote

        Returns
        -------
        tuple
          stdout, stderr
        """
        ssh_cmd = ["ssh", "-S", self.ctrl_master, self.host]
        ssh_cmd += cmd if isinstance(cmd, list) \
            else sh_split(cmd, posix=not on_windows)
        # TODO: expect parameters
        return self.runner.run(ssh_cmd, expect_fail=True, expect_stderr=True)

