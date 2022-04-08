.. _man_datalad-shell-completion:

datalad shell-completion
========================

Synopsis
--------
::

  datalad shell-completion [-h] [--version]

Description
-----------
Display shell script for enabling shell completion for DataLad.

Output of this command should be "sourced" by the bash or zsh to enable
shell completions provided by argcomplete.

Example:

    $ source <(datalad shell-completion)
    $ datalad --<PRESS TAB to display available option>


Options
-------
**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
