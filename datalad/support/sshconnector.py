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

from six.moves.urllib.parse import urlparse

from datalad.support.gitrepo import GitRepo
from datalad.utils import not_supported_on_windows
from datalad.utils import assure_dir
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.sshconnector')


class SSHConnector(object):
    """Representation of a ssh connection.
    """

    def __init__(self, url=None, repo=None):
        not_supported_on_windows("TODO: Make SSHConnector an abstraction to "
                                 "interface platform dependent SSH")
        self.runner = Runner()

        if url:
            self.connect(url)
        if repo:
            self.use_with_git(repo)

    def connect(self, url=None, dir=None):

        # parse url:
        parsed_target = urlparse(url)
        if parsed_target.scheme != 'ssh':
            raise ValueError("Not an SSH URL: %s" % url)
        self.host = parsed_target.netloc
        if not self.host:
            raise ValueError("Malformed URL (missing host): %s" % url)
        if dir is None:
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

        # TODO: test for pwd; --force creates it; cd to pwd

    def use_with_repo(self, repo=None):
        if not isinstance(repo, GitRepo):
            raise ValueError("Don't know how to handle repo of type '%s'" %
                             type(repo))
        from pkg_resources import resource_filename
        repo.cmd_call_wrapper.env["GIT_SSH"] = resource_filename('datalad',
                                                    'resources/git_ssh.sh')
        # TODO: How to deal with gitpython?
        # TODO: Maybe make it a method of GitRepo instead

    def run_on_remote(self, cmd):
        ssh_cmd = ["ssh", "-S", self.ctrl_master, self.host]
        if isinstance(cmd, list):
            command = ssh_cmd + cmd
        else:
            # what does shlex correctly handle?
            pass
        self.runner.run(command)

