.. _man_datalad-run:

datalad run
===========

Synopsis
--------
::

  datalad run [-h] [-d DATASET] [-i PATH] [-o PATH] [--expand {inputs|outputs|both}]
      [--assume-ready {inputs|outputs|both}] [--explicit] [-m MESSAGE]
      [--sidecar {yes|no}] [--dry-run {basic|command}] [-J NJOBS]
      [--version] ...

Description
-----------
Run an arbitrary shell command and record its impact on a dataset.

It is recommended to craft the command such that it can run in the root
directory of the dataset that the command will be recorded in. However,
as long as the command is executed somewhere underneath the dataset root,
the exact location will be recorded relative to the dataset root.

If the executed command did not alter the dataset in any way, no record of
the command execution is made.

If the given command errors, a COMMANDERROR exception with the same exit
code will be raised, and no modifications will be saved.

*Command format*

A few placeholders are supported in the command via Python format
specification. "{pwd}" will be replaced with the full path of the
current working directory. "{dspath}" will be replaced with the full
path of the dataset that run is invoked on. "{tmpdir}" will be
replaced with the full path of a temporary directory. "{inputs}" and
"{outputs}" represent the values specified by --input and --output. If
multiple values are specified, the values will be joined by a space.
The order of the values will match that order from the command line,
with any globs expanded in alphabetical order (like bash). Individual
values can be accessed with an integer index (e.g., "{inputs[0]}").

Note that the representation of the inputs or outputs in the formatted
command string depends on whether the command is given as a list of
arguments or as a string (quotes surrounding the command). The
concatenated list of inputs or outputs will be surrounded by quotes
when the command is given as a list but not when it is given as a
string. This means that the string form is required if you need to
pass each input as a separate argument to a preceding script (i.e.,
write the command as "./script {inputs}", quotes included). The string
form should also be used if the input or output paths contain spaces
or other characters that need to be escaped.

To escape a brace character, double it (i.e., "{{" or "}}").

Custom placeholders can be added as configuration variables under
"datalad.run.substitutions".  As an example:

  Add a placeholder "name" with the value "joe"::

    % git config --file=.datalad/config datalad.run.substitutions.name joe
    % datalad save -m "Configure name placeholder" .datalad/config

  Access the new placeholder in a command::

    % datalad run "echo my name is {name} >me"

*Examples*

Run an executable script and record the impact on a dataset::

   % datalad run -m 'run my script' 'code/script.sh'

Run a command and specify a directory as a dependency for the run. The
contents of the dependency will be retrieved prior to running the
script::

   % datalad run -m 'run my script' -i 'data/*' 'code/script.sh'

Run an executable script and specify output files of the script to be
unlocked prior to running the script::

   % datalad run -m 'run my script' -i 'data/*' \
     -o 'output_dir/*' 'code/script.sh'

Specify multiple inputs and outputs::

   % datalad run -m 'run my script' -i 'data/*' \
     -i 'datafile.txt' -o 'output_dir/*' -o \
     'outfile.txt' 'code/script.sh'

Use ** to match any file at any directory depth recursively. Single *
does not check files within matched directories.::

   % datalad run -m 'run my script' -i 'data/**/*.dat' \
     -o 'output_dir/**' 'code/script.sh'




Options
-------
COMMAND
~~~~~~~
command for execution. A leading '--' can be used to disambiguate this command from the preceding options to DataLad.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to record the command results in. An attempt is made to identify the dataset based on the current working directory. If a dataset is given, the command will be executed in the root directory of this dataset. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-i** PATH, **-\\-input** PATH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A dependency for the run. Before running the command, the content of this file will be retrieved. A value of "." means "run datalad get .". The value can also be a glob. This option can be given more than once.

**-o** PATH, **-\\-output** PATH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Prepare this file to be an output file of the command. A value of "." means "run datalad unlock ." (and will fail if some content isn't present). For any other value, if the content of this file is present, unlock the file. Otherwise, remove it. The value can also be a glob. This option can be given more than once.

**-\\-expand** {inputs|outputs|both}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Expand globs when storing inputs and/or outputs in the commit message. Constraints: value must be one of ('inputs', 'outputs', 'both')

**-\\-assume-ready** {inputs|outputs|both}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Assume that inputs do not need to be retrieved and/or outputs do not need to unlocked or removed before running the command. This option allows you to avoid the expense of these preparation steps if you know that they are unnecessary. Constraints: value must be one of ('inputs', 'outputs', 'both')

**-\\-explicit**
~~~~~~~~~~~~~~~~
Consider the specification of inputs and outputs to be explicit. Don't warn if the repository is dirty, and only save modifications to the listed outputs.

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
a description of the state or the changes made to a dataset. Constraints: value must be a string

**-\\-sidecar** {yes|no}
~~~~~~~~~~~~~~~~~~~~~~~~
By default, the configuration variable 'datalad.run.record-sidecar' determines whether a record with information on a command's execution is placed into a separate record file instead of the commit message (default: off). This option can be used to override the configured behavior on a case-by-case basis. Sidecar files are placed into the dataset's '.datalad/runinfo' directory (customizable via the 'datalad.run.record-directory' configuration variable). Constraints: value must be NONE, or value must be convertible to type bool

**-\\-dry-run** {basic|command}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Do not run the command; just display details about the command execution. A value of "basic" reports a few important details about the execution, including the expanded command and expanded inputs and outputs. "command" displays the expanded command only. Note that input and output globs underneath an uninstalled dataset will be left unexpanded because no subdatasets will be installed for a dry run. Constraints: value must be one of ('basic', 'command')

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
