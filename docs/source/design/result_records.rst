.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_result_records:

**************
Result records
**************

.. topic:: Specification scope and status

   This specification describes the current implementation.

Result records are the standard return value format for all DataLad commands.
Each command invocation yields one or more result records. Result records are
routinely inspected throughout the code base, and are used to inform generic
error handling, as well as particular calling commands on how to proceed with
a specific operation.

The technical implementation of a result record is a Python dictionary.  This
dictionary must contain a number of mandatory fields/keys (see below). However,
an arbitrary number of additional fields may be added to a result record.

The ``get_status_dict()`` function simplifies the creation of result records.

.. note::
   Developers *must* compose result records with care! DataLad supports custom
   user-provided hook configurations that use result record fields to
   decide when to trigger a custom post-result operation. Such custom hooks
   rely on a persistent naming and composition of result record fields.
   Changes to result records, including field name changes, field value changes,
   but also timing/order of record emitting potentially break user set ups!


Mandatory fields
================

The following keys *must* be present in any result record. If any of these
keys is missing, DataLad's behavior is undefined.


``action``
----------

A string label identifying which type of operation a result is associated with.
Labels *must not* contain white space. They should be compact, and lower-cases,
and use ``_`` (underscore) to separate words in compound labels.

A result without an ``action`` label will not be processed and is discarded.


``path``
--------

A string with an *absolute* path describing the local entity a result is
associated with. Paths must be platform-specific (e.g., Windows paths on
Windows, and POSIX paths on other operating systems). When a result is about an
entity that has no meaningful relation to the local file system (e.g., a URL to
be downloaded), to ``path`` value should be determined with respect to the
potential impact of the result on any local entity (e.g., a URL downloaded
to a local file path, a local dataset modified based on remote information).


``status``
----------

This field indicates the nature of a result in terms of four categories, identified
by a string label.

- ``ok``: a standard, to-be-expected result
- ``notneeded``: an operation that was requested, but found to be unnecessary
  in order to achieve a desired goal
- ``impossible``: a requested operation cannot be performed, possibly because
  its preconditions are not met
- ``error``: an error occurred while performing an operation

Based on the ``status`` field, a result is categorized into *success* (``ok``,
``notneeded``) and *failure* (``impossible``, ``error``). Depending on the
``on_failure`` parameterization of a command call, any failure-result emitted
by a command can lead to an ``IncompleteResultsError`` being raised on command
exit, or a non-zero exit code on the command line. With ``on_failure='stop'``,
an operation is halted on the first failure and the command errors out
immediately, with ``on_failure='continue'`` an operation will continue despite
intermediate failures and the command only errors out at the very end, with
``on_failure='ignore'`` the command will not error even when failures occurred.
The latter mode can be used in cases where the initial status-characterization
needs to be corrected for the particular context of an operation (e.g., to
relabel expected and recoverable errors).


Common optional fields
======================

The following fields are not required, but can be used to enrich a result
record with additional information that improves its interpretability, or
triggers particular optional functionality in generic result processing.


``type``
--------

This field indicates the type of entity a result is associated with. This may
or may not be the type of the local entity identified by the ``path`` value.
The following values are common, and should be used in matching cases, but
arbitrary other values are supported too:

- ``dataset``: a DataLad dataset
- ``file``: a regular file
- ``directory``: a directory
- ``symlink``: a symbolic link
- ``key``: a git-annex key
- ``sibling``: a Dataset sibling or Git remote


``message``
-----------

A message providing additional human-readable information on the nature or
provenance of a result. Any non-``ok`` results *should* have a message providing
information on the rational of their status characterization.

A message can be a string or a tuple. In case of a tuple, the second item can
contain values for ``%``-expansion of the message string. Expansion is performed
only immediately prior to actually outputting the message, hence string formatting
runtime costs can be avoided this way, if a message is not actually shown.


``logger``
----------

If a result record has a ``message`` field, then a given `Logger` instance
(typically from ``logging.getLogger()``) will be used to automatically log
this message. The log channel/level is determined based on
``datalad.log.result-level`` configuration setting. By default, this is
the ``debug`` level. When set to ``match-status`` the log level is determined
based on the ``status`` field of a result record:

- ``debug`` for ``'ok'``, and ``'notneeded'`` results
- ``warning`` for ``'impossible'`` results
- ``error`` for ``'error'`` results

This feature should be used with care. Unconditional logging can lead to
confusing double-reporting when results rendered and also visibly logged.


``refds``
---------

This field can identify a path (using the same semantics and requirements as
the ``path`` field) to a reference dataset that represents the larger context
of an operation. For example, when recursively processing multiple files across
a number of subdatasets, a ``refds`` value may point to the common superdataset.
This value may influence, for example, how paths are rendered in user-output.


``parentds``
------------

This field can identify a path (using the same semantics and requirements as
the ``path`` field) to a dataset containing an entity.


``state``
---------

A string label categorizing the state of an entity. Common values are:

- ``clean``
- ``untracked``
- ``modified``
- ``deleted``
- ``absent``
- ``present``


``error-messages``
------------------

List of any error messages that were captured or produced while achieving a
result.


``exception``
-------------

An exception that occurred while achieving the reported result.


``exception_traceback``
-----------------------

A string with a traceback for the exception reported in ``exception``.


Additional fields observed "in the wild"
========================================

Given that arbitrary fields are supported in result records, it is impossible
to compose a comprehensive list of field names (keys). However, in order to
counteract needless proliferation, the following list describes fields that
have been observed in implementations. Developers are encouraged to preferably
use compatible names from this list, or extend the list for additional items.

In alphabetical order:

``bytesize``
  The size of an entity in bytes (integer).

``gitshasum``
  SHA1 of an entity (string)

``prev_gitshasum``
  SHA1 of a previous state of an entity (string)

``key``
  The git-annex key associated with a ``type``-``file`` entity.
