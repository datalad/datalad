.. _man_datalad:

datalad
=======

Synopsis
--------
::

  datalad [-l LEVEL] [-C PATH] [--version] [--dbg] [--idbg] [-c KEY=VALUE] [-f
      {generic,json,json_pp,tailored,disabled,'<template>'}]
      [--report-status
      {success,failure,ok,notneeded,impossible,error}] [--report-type
      {dataset,file}] [--on-failure {ignore,continue,stop}] [--cmd]
      [-h] {create-sibling-github,create-sibling-gitlab,create-sibling
      -gogs,create-sibling-gin,create-sibling-gitea,create-sibling-ria
      ,create-sibling,siblings,update,search,metadata,aggregate-metada
      ta,extract-metadata,subdatasets,drop,remove,addurls,copy-file,do
      wnload-url,foreach-dataset,install,rerun,run-procedure,create,sa
      ve,status,clone,get,push,run,diff,wtf,clean,add-archive-content,
      add-readme,export-archive,export-archive-ora,export-to-figshare,
      no-annex,check-dates,unlock,uninstall,create-test-dataset,sshrun
      ,test,shell-completion} ...

Description
-----------
Comprehensive data management solution

DataLad provides a unified data distribution system built on the Git
and Git-annex. DataLad command line tools allow to manipulate (obtain,
create, update, publish, etc.) datasets and provide a comprehensive
toolbox for joint management of data and code. Compared to Git/annex
it primarily extends their functionality to transparently and
simultaneously work with multiple inter-related repositories.


Options
-------
{create-sibling-github,create-sibling-gitlab,create-sibling-gogs,create-sibling-gin,create-sibling-gitea,create-sibling-ria,create-sibling,siblings,update,search,metadata,aggregate-metadata,extract-metadata,subdatasets,drop,remove,addurls,copy-file,download-url,foreach-dataset,install,rerun,run-procedure,create,save,status,clone,get,push,run,diff,wtf,clean,add-archive-content,add-readme,export-archive,export-archive-ora,export-to-figshare,no-annex,check-dates,unlock,uninstall,create-test-dataset,sshrun,test,shell-completion}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**-l** LEVEL, **-\\-log-level** LEVEL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
set logging verbosity level. Choose among critical, error, warning, info, debug. Also you can specify an integer <10 to provide even more debugging information

**-C** PATH
~~~~~~~~~~~
run as if datalad was started in <path> instead of the current working directory. When multiple -C options are given, each subsequent non-absolute -C <path> is interpreted relative to the preceding -C <path>. This option affects the interpretations of the path names in that they are made relative to the working directory caused by the -C option

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

**-\\-dbg**
~~~~~~~~~~~
enter Python debugger when uncaught exception happens

**-\\-idbg**
~~~~~~~~~~~~
enter IPython debugger when uncaught exception happens

**-c** KEY=VALUE
~~~~~~~~~~~~~~~~
configuration variable setting. Overrides any configuration read from a file, but is potentially overridden itself by configuration variables in the process environment.

**-f** {generic,json,json_pp,tailored,disabled,'<template>'}, **-\\-output-format** {generic,json,json_pp,tailored,disabled,'<template>'}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
select rendering mode command results. 'tailored' enables a command-specific rendering style that is typically tailored to human consumption, if there is one for a specific command, or otherwise falls back on the the 'generic' result renderer; 'generic' renders each result in one line with key info like action, status, path, and an optional message); 'json' a complete JSON line serialization of the full result record; 'json_pp' like 'json', but pretty- printed spanning multiple lines; 'disabled' turns off result rendering entirely; '<template>' reports any value(s) of any result properties in any format indicated by the template (e.g. '{path}', compare with JSON output for all key- value choices). The template syntax follows the Python "format() language". It is possible to report individual dictionary values, e.g. '{metadata[name]}'. If a 2nd-level key contains a colon, e.g. 'music:Genre', ':' must be substituted by '#' in the template, like so: '{metadata[music#Genre]}'. [Default: 'tailored']

**-\\-report-status** {success,failure,ok,notneeded,impossible,error}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
constrain command result report to records matching the given status. 'success' is a synonym for 'ok' OR 'notneeded', 'failure' stands for 'impossible' OR 'error'.

**-\\-report-type** {dataset,file}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
constrain command result report to records matching the given type. Can be given more than once to match multiple types.

**-\\-on-failure** {ignore,continue,stop}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
when an operation fails: 'ignore' and continue with remaining operations, the error is logged but does not lead to a non-zero exit code of the command; 'continue' works like 'ignore', but an error causes a non-zero exit code; 'stop' halts on first failure and yields non-zero exit code. A failure is any result with status 'impossible' or 'error'. [Default: 'continue']

**-\\-cmd**
~~~~~~~~~~~
syntactical helper that can be used to end the list of global command line options before the subcommand label. Options taking an arbitrary number of arguments may require to be followed by a single --cmd in order to enable identification of the subcommand.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

"Be happy!"

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
