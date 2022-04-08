.. _man_datalad-download-url:

datalad download-url
====================

Synopsis
--------
::

  datalad download-url [-h] [-d PATH] [-O PATH] [-o] [--archive] [--nosave] [-m MESSAGE]
      [--version] url [url ...]

Description
-----------
Download content

It allows for a uniform download interface to various supported URL
schemes (see command help for details), re-using or asking for
authentication details maintained by datalad.

*Examples*

Download files from an http and S3 URL::

   % datalad download-url http://example.com/file.dat s3://bucket/file2.dat

Download a file to a path and provide a commit message::

   % datalad download-url -m 'added a file' -O myfile.dat \
     s3://bucket/file2.dat

Append a trailing slash to the target path to download into a
specified directory::

   % datalad download-url --path=data/ http://example.com/file.dat

Leave off the trailing slash to download into a regular file::

   % datalad download-url --path=data http://example.com/file.dat




Options
-------
url
~~~
URL(s) to be downloaded. Supported protocols: 'ftp', 'http', 'https', 's3', 'shub'. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** PATH, **-\\-dataset** PATH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to add files to. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Use --nosave to prevent adding files to the dataset. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-O** *PATH*, **-\\-path** *PATH*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
target for download. If the path has a trailing separator, it is treated as a directory, and each specified URL is downloaded under that directory to a base name taken from the URL. Without a trailing separator, the value specifies the name of the downloaded file (file name extensions inferred from the URL may be added to it, if they are not yet present) and only a single URL should be given. In both cases, leading directories will be created if needed. This argument defaults to the current directory. Constraints: value must be a string

**-o**, **-\\-overwrite**
~~~~~~~~~~~~~~~~~~~~~~~~~
flag to overwrite it if target file exists.

**-\\-archive**
~~~~~~~~~~~~~~~
pass the downloaded files to datalad add-archive-content --delete.

**-\\-nosave**
~~~~~~~~~~~~~~
by default all modifications to a dataset are immediately saved. Giving this option will disable this behavior.

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
a description of the state or the changes made to a dataset. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
