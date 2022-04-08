.. _man_datalad-sshrun:

datalad sshrun
==============

Synopsis
--------
::

  datalad sshrun [-h] [-p PORT] [-4] [-6] [-o OPTION] [-n] [--version] login cmd

Description
-----------
Run command on remote machines via SSH.

This is a replacement for a small part of the functionality of SSH.
In addition to SSH alone, this command can make use of datalad's SSH
connection management. Its primary use case is to be used with Git
as 'core.sshCommand' or via "GIT_SSH_COMMAND".

Configure `datalad.ssh.identityfile` to pass a file to the ssh's -i option.


Options
-------
login
~~~~~
[user@]hostname.

cmd
~~~
command for remote execution.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-p** *PORT*, **-\\-port** *PORT*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
port to connect to on the remote host.

**-4**
~~~~~~
use IPv4 addresses only.

**-6**
~~~~~~
use IPv6 addresses only.

**-o** OPTION
~~~~~~~~~~~~~
configuration option passed to SSH.

**-n**
~~~~~~
Do not connect stdin to the process.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
