.. _man_datalad-add-readme:

datalad add-readme
==================

Synopsis
--------
::

  datalad add-readme [-h] [-d DATASET] [--existing {skip|append|replace}] [--version]
      [PATH]

Description
-----------
Add basic information about DataLad datasets to a README file

The README file is added to the dataset and the addition is saved
in the dataset.
Note: Make sure that no unsaved modifications to your dataset's
.gitattributes file exist.


Options
-------
PATH
~~~~
Path of the README file within the dataset. Constraints: value must be a string [Default: 'README.md']

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Dataset to add information to. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-existing** {skip|append|replace}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
How to react if a file with the target name already exists: 'skip': do nothing; 'append': append information to the existing file; 'replace': replace the existing file with new content. Constraints: value must be one of ('skip', 'append', 'replace') [Default: 'skip']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
