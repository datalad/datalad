.. _man_datalad-wtf:

datalad wtf
===========

Synopsis
--------
::

  datalad wtf [-h] [-d DATASET] [-s {some|all}] [-S SECTION] [--flavor {full|short}]
      [-D DECOR] [-c] [--version]

Description
-----------
Generate a report about the DataLad installation and configuration

IMPORTANT: Sharing this report with untrusted parties (e.g. on the web)
should be done with care, as it may include identifying information, and/or
credentials or access tokens.


Options
-------
**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"specify the dataset to report on. no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-s** {some|all}, **-\\-sensitive** {some|all}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if set to 'some' or 'all', it will display sections such as config and metadata which could potentially contain sensitive information (credentials, names, etc.). If 'some', the fields which are known to be sensitive will still be masked out. Constraints: value must be one of ('some', 'all')

**-S** SECTION, **-\\-section** SECTION
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
section to include. If not set - depends on flavor. '*' could be used to force all sections. This option can be given multiple times. Constraints: value must be one of ('configuration', 'credentials', 'datalad', 'dataset', 'dependencies', 'environment', 'extensions', 'git-annex', 'location', 'metadata_extractors', 'metadata_indexers', 'python', 'system', '*')

**-\\-flavor** {full|short}
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Flavor of WTF. 'full' would produce markdown with exhaustive list of sections. 'short' will provide a condensed summary only of datalad and dependencies by default. Use --section to list other sections. Constraints: value must be one of ('full', 'short') [Default: 'full']

**-D** *DECOR*, **-\\-decor** *DECOR*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
decoration around the rendering to facilitate embedding into issues etc, e.g. use 'html_details' for posting collapsible entry to GitHub issues. Constraints: value must be one of ('html_details',)

**-c**, **-\\-clipboard**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, do not print but copy to clipboard (requires pyperclip module).

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
