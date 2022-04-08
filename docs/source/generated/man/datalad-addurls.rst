.. _man_datalad-addurls:

datalad addurls
===============

Synopsis
--------
::

  datalad addurls [-h] [-d DATASET] [-t TYPE] [-x REGEXP] [-m FORMAT] [--key FORMAT]
      [--message MESSAGE] [-n] [--fast] [--ifexists {overwrite|skip}]
      [--missing-value VALUE] [--nosave] [--version-urls] [-c PROC]
      [-J NJOBS] [--drop-after] [--on-collision
      {error|error-if-different|take-first|take-last}] [--version]
      URL-FILE URL-FORMAT FILENAME-FORMAT

Description
-----------
Create and update a dataset from a list of URLs.

*Format specification*

Several arguments take format strings.  These are similar to normal Python
format strings where the names from `URL-FILE` (column names for a comma-
or tab-separated file or properties for JSON) are available as
placeholders. If `URL-FILE` is a CSV or TSV file, a positional index can
also be used (i.e., "{0}" for the first column). Note that a placeholder
cannot contain a ':' or '!'.

In addition, the `FILENAME-FORMAT` arguments has a few special
placeholders.

  - _repindex

    The constructed file names must be unique across all fields rows.  To
    avoid collisions, the special placeholder "_repindex" can be added to
    the formatter.  Its value will start at 0 and increment every time a
    file name repeats.

  - _url_hostname, _urlN, _url_basename*

    Various parts of the formatted URL are available.  Take
    "http://datalad.org/asciicast/seamless_nested_repos.sh" as an example.

    "datalad.org" is stored as "_url_hostname".  Components of the URL's
    path can be referenced as "_urlN".  "_url0" and "_url1" would map to
    "asciicast" and "seamless_nested_repos.sh", respectively.  The final
    part of the path is also available as "_url_basename".

    This name is broken down further.  "_url_basename_root" and
    "_url_basename_ext" provide access to the root name and extension.
    These values are similar to the result of os.path.splitext, but, in the
    case of multiple periods, the extension is identified using the same
    length heuristic that git-annex uses.  As a result, the extension of
    "file.tar.gz" would be ".tar.gz", not ".gz".  In addition, the fields
    "_url_basename_root_py" and "_url_basename_ext_py" provide access to
    the result of os.path.splitext.

  - _url_filename*

    These are similar to _url_basename* fields, but they are obtained with
    a server request.  This is useful if the file name is set in the
    Content-Disposition header.


*Examples*

Consider a file "avatars.csv" that contains::

    who,ext,link
    neurodebian,png,https://avatars3.githubusercontent.com/u/260793
    datalad,png,https://avatars1.githubusercontent.com/u/8927200

To download each link into a file name composed of the 'who' and 'ext'
fields, we could run::

  $ datalad addurls -d avatar_ds --fast avatars.csv '{link}' '{who}.{ext}'

The `-d avatar_ds` is used to create a new dataset in "$PWD/avatar_ds".

If we were already in a dataset and wanted to create a new subdataset in an
"avatars" subdirectory, we could use "//" in the `FILENAME-FORMAT`
argument::

  $ datalad addurls --fast avatars.csv '{link}' 'avatars//{who}.{ext}'

If the information is represented as JSON lines instead of comma separated
values or a JSON array, you can use a utility like jq to transform the JSON
lines into an array that addurls accepts::

  $ ... | jq --slurp . | datalad addurls - '{link}' '{who}.{ext}'

NOTE

   For users familiar with 'git annex addurl': A large part of this
   plugin's functionality can be viewed as transforming data from
   `URL-FILE` into a "url filename" format that fed to 'git annex addurl
   --batch --with-files'.


Options
-------
URL-FILE
~~~~~~~~
A file that contains URLs or information that can be used to construct URLs. Depending on the value of --input-type, this should be a comma- or tab-separated file (with a header as the first row) or a JSON file (structured as a list of objects with string values). If '-', read from standard input, taking the content as JSON when --input-type is at its default value of 'ext'.

URL-FORMAT
~~~~~~~~~~
A format string that specifies the URL for each entry. See the 'Format Specification' section above.

FILENAME-FORMAT
~~~~~~~~~~~~~~~
Like `URL-FORMAT`, but this format string specifies the file to which the URL's content will be downloaded. The name should be a relative path and will be taken as relative to the top-level dataset, regardless of whether it is specified via --dataset or inferred. The file name may contain directories. The separator "//" can be used to indicate that the left-side directory should be created as a new subdataset. See the 'Format Specification' section above.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Add the URLs to this dataset (or possibly subdatasets of this dataset). An empty or non-existent directory is passed to create a new dataset. New subdatasets can be specified with `FILENAME-FORMAT`. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-t** TYPE, **-\\-input-type** TYPE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Whether `URL-FILE` should be considered a CSV file, TSV file, or JSON file. The default value, "ext", means to consider `URL-FILE` as a JSON file if it ends with ".json" or a TSV file if it ends with ".tsv". Otherwise, treat it as a CSV file. Constraints: value must be one of ('ext', 'csv', 'tsv', 'json') [Default: 'ext']

**-x** REGEXP, **-\\-exclude-autometa** REGEXP
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, metadata field=value pairs are constructed with each column in `URL- FILE`, excluding any single column that is specified via `URL-FORMAT`. This argument can be used to exclude columns that match a regular expression. If set to '*' or an empty string, automatic metadata extraction is disabled completely. This argument does not affect metadata set explicitly with --meta.

**-m** FORMAT, **-\\-meta** FORMAT
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A format string that specifies metadata. It should be structured as "<field>=<value>". As an example, "location={3}" would mean that the value for the "location" metadata field should be set the value of the fourth column. This option can be given multiple times.

**-\\-key** FORMAT
~~~~~~~~~~~~~~~~~~
A format string that specifies an annex key for the file content. In this case, the file is not downloaded; instead the key is used to create the file without content. The value should be structured as "[et:]<input backend>[-s<bytes>]--<hash>". The optional "et:" prefix, which requires git- annex 8.20201116 or later, signals to toggle extension state of the input backend (i.e., MD5 vs MD5E). As an example, "et:MD5-s{size}--{md5sum}" would use the 'md5sum' and 'size' columns to construct the key, migrating the key from MD5 to MD5E, with an extension based on the file name. Note: If the *input* backend itself is an annex extension backend (i.e., a backend with a trailing "E"), the key's extension will not be updated to match the extension of the corresponding file name. Thus, unless the input keys and file names are generated from git- annex, it is recommended to avoid using extension backends as input. If an extension is desired, use the plain variant as input and prepend "et:" so that git-annex will migrate from the plain backend to the extension variant.

**-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~
Use this message when committing the URL additions. Constraints: value must be NONE, or value must be a string

**-n**, **-\\-dry-run**
~~~~~~~~~~~~~~~~~~~~~~~
Report which URLs would be downloaded to which files and then exit.

**-\\-fast**
~~~~~~~~~~~~
If True, add the URLs, but don't download their content. Underneath, this passes the --fast flag to `git annex addurl`.

**-\\-ifexists** {overwrite|skip}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
What to do if a constructed file name already exists. The default behavior is to proceed with the `git annex addurl`, which will fail if the file size has changed. If set to 'overwrite', remove the old file before adding the new one. If set to 'skip', do not add the new file. Constraints: value must be one of ('overwrite', 'skip')

**-\\-missing-value** VALUE
~~~~~~~~~~~~~~~~~~~~~~~~~~~
When an empty string is encountered, use this value instead. Constraints: value must be NONE, or value must be a string

**-\\-nosave**
~~~~~~~~~~~~~~
by default all modifications to a dataset are immediately saved. Giving this option will disable this behavior.

**-\\-version-urls**
~~~~~~~~~~~~~~~~~~~~
Try to add a version ID to the URL. This currently only has an effect on HTTP URLs for AWS S3 buckets. s3:// URL versioning is not yet supported, but any URL that already contains a "versionId=" parameter will be used as is.

**-c** PROC, **-\\-cfg-proc** PROC
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pass this --cfg_proc value when calling CREATE to make datasets.

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-drop-after**
~~~~~~~~~~~~~~~~~~
drop files after adding to annex.

**-\\-on-collision** {error|error-if-different|take-first|take-last}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
What to do when more than one row produces the same file name. By default an error is triggered. "error-if-different" suppresses that error if rows for a given file name collision have the same URL and metadata. "take-first" or "take- last" indicate to instead take the first row or last row from each set of colliding rows. Constraints: value must be one of ('error', 'error-if- different', 'take-first', 'take-last') [Default: 'error']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
