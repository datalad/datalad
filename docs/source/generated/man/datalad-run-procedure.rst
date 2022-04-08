.. _man_datalad-run-procedure:

datalad run-procedure
=====================

Synopsis
--------
::

  datalad run-procedure [-h] [-d PATH] [--discover] [--help-proc] [--version] ...

Description
-----------
Run prepared procedures (DataLad scripts) on a dataset

*Concept*

A "procedure" is an algorithm with the purpose to process a dataset in a
particular way. Procedures can be useful in a wide range of scenarios,
like adjusting dataset configuration in a uniform fashion, populating
a dataset with particular content, or automating other routine tasks,
such as synchronizing dataset content with certain siblings.

Implementations of some procedures are shipped together with DataLad,
but additional procedures can be provided by 1) any DataLad extension,
2) any (sub-)dataset, 3) a local user, or 4) a local system administrator.
DataLad will look for procedures in the following locations and order:

Directories identified by the configuration settings

- 'datalad.locations.user-procedures' (determined by
  platformdirs.user_config_dir; defaults to '$HOME/.config/datalad/procedures'
  on GNU/Linux systems)
- 'datalad.locations.system-procedures' (determined by
  platformdirs.site_config_dir; defaults to '/etc/xdg/datalad/procedures' on
  GNU/Linux systems)
- 'datalad.locations.dataset-procedures'

and subsequently in the 'resources/procedures/' directories of any
installed extension, and, lastly, of the DataLad installation itself.

Please note that a dataset that defines
'datalad.locations.dataset-procedures' provides its procedures to
any dataset it is a subdataset of. That way you can have a collection of
such procedures in a dedicated dataset and install it as a subdataset into
any dataset you want to use those procedures with. In case of a naming
conflict with such a dataset hierarchy, the dataset you're calling
run-procedures on will take precedence over its subdatasets and so on.

Each configuration setting can occur multiple times to indicate multiple
directories to be searched. If a procedure matching a given name is found
(filename without a possible extension), the search is aborted and this
implementation will be executed. This makes it possible for individual
datasets, users, or machines to override externally provided procedures
(enabling the implementation of customizable processing "hooks").


*Procedure implementation*

A procedure can be any executable. Executables must have the appropriate
permissions and, in the case of a script, must contain an appropriate
"shebang" line. If a procedure is not executable, but its filename ends
with '.py', it is automatically executed by the 'python' interpreter
(whichever version is available in the present environment). Likewise,
procedure implementations ending on '.sh' are executed via 'bash'.

Procedures can implement any argument handling, but must be capable
of taking at least one positional argument (the absolute path to the
dataset they shall operate on).

For further customization there are two configuration settings per procedure
available:

- 'datalad.procedures.<NAME>.call-format'
  fully customizable format string to determine how to execute procedure
  NAME (see also datalad-run).
  It currently requires to include the following placeholders:

  - '{script}': will be replaced by the path to the procedure
  - '{ds}': will be replaced by the absolute path to the dataset the
    procedure shall operate on
  - '{args}': (not actually required) will be replaced by
    all additional arguments passed into run-procedure after NAME
    
    As an example the default format string for a call to a python script is:
    "python {script} {ds} {args}"
- 'datalad.procedures.<NAME>.help'
  will be shown on `datalad run-procedure --help-proc NAME` to provide a
  description and/or usage info for procedure NAME

*Examples*

Find out which procedures are available on the current system::

   % datalad run-procedure --discover

Run the 'yoda' procedure in the current dataset::

   % datalad run-procedure cfg_yoda




Options
-------
NAME [ARGS]
~~~~~~~~~~~
Name and possibly additional arguments of the to-be-executed procedure. [PY: Can also be a dictionary coming from run-procedure(discover=True).]Note, that all options to run-procedure need to be put before NAME, since all ARGS get assigned to NAME.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** PATH, **-\\-dataset** PATH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to run the procedure on. An attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-discover**
~~~~~~~~~~~~~~~~
if given, all configured paths are searched for procedures and one result record per discovered procedure is yielded, but no procedure is executed.

**-\\-help-proc**
~~~~~~~~~~~~~~~~~
if given, get a help message for procedure NAME from config setting datalad.procedures.NAME.help.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
