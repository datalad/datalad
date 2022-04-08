.. _man_datalad-check-dates:

datalad check-dates
===================

Synopsis
--------
::

  datalad check-dates [-h] [-D DATE] [--rev REVISION] [--annex {all|tree|none}] [--no-tags]
      [--older] [--version] [PATH ...]

Description
-----------
Find repository dates that are more recent than a reference date.

The main purpose of this tool is to find "leaked" real dates in
repositories that are configured to use fake dates. It checks dates from
three sources: (1) commit timestamps (author and committer dates), (2)
timestamps within files of the "git-annex" branch, and (3) the timestamps
of annotated tags.


Options
-------
PATH
~~~~
Root directory in which to search for Git repositories. The current working directory will be used by default. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-D** DATE, **-\\-reference-date** DATE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Compare dates to this date. If dateutil is installed, this value can be any format that its parser recognizes. Otherwise, it should be a unix timestamp that starts with a "@". The default value corresponds to 01 Jan, 2018 00:00:00 -0000. Constraints: value must be a string [Default: '@1514764800']

**-\\-rev** REVISION
~~~~~~~~~~~~~~~~~~~~
Search timestamps from commits that are reachable from REVISION. Any revision specification supported by git log, including flags like --all and --tags, can be used. This option can be given multiple times.

**-\\-annex** {all|tree|none}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode for "git-annex" branch search. If 'all', all blobs within the branch are searched. 'tree' limits the search to blobs that are referenced by the tree at the tip of the branch. 'none' disables search of "git-annex" blobs. Constraints: value must be one of ('all', 'tree', 'none') [Default: 'all']

**-\\-no-tags**
~~~~~~~~~~~~~~~
Don't check the dates of annotated tags.

**-\\-older**
~~~~~~~~~~~~~
Find dates which are older than the reference date rather than newer.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
