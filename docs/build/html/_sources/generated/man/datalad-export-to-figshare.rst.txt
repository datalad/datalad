.. _man_datalad-export-to-figshare:

datalad export-to-figshare
==========================

Synopsis
--------
::

  datalad export-to-figshare [-h] [-d DATASET] [--missing-content {error|continue|ignore}]
      [--no-annex] [--article-id ID] [--version] [PATH]

Description
-----------
Export the content of a dataset as a ZIP archive to figshare

Very quick and dirty approach.  Ideally figshare should be supported as
a proper git annex special remote.  Unfortunately, figshare does not support
having directories, and can store only a flat list of files.  That makes
it impossible for any sensible publishing of complete datasets.

The only workaround is to publish dataset as a zip-ball, where the entire
content is wrapped into a .zip archive for which figshare would provide a
navigator.


Options
-------
PATH
~~~~
File name of the generated ZIP archive. If no file name is given the archive will be generated in the top directory of the dataset and will be named: datalad_<dataset_uuid>.zip. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"specify the dataset to export. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-missing-content** {error|continue|ignore}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, any discovered file with missing content will result in an error and the plugin is aborted. Setting this to 'continue' will issue warnings instead of failing on error. The value 'ignore' will only inform about problem at the 'debug' log level. The latter two can be helpful when generating a TAR archive from a dataset where some file content is not available locally. Constraints: value must be one of ('error', 'continue', 'ignore') [Default: 'error']

**-\\-no-annex**
~~~~~~~~~~~~~~~~
By default the generated .zip file would be added to annex, and all files would get registered in git-annex to be available from such a tarball. Also upon upload we will register for that archive to be a possible source for it in annex. Setting this flag disables this behavior.

**-\\-article-id** ID
~~~~~~~~~~~~~~~~~~~~~
Which article to publish to. Constraints: value must be convertible to type 'int'

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
