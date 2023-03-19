.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_user_messaging:

*******************************************************
User messaging: result records vs exceptions vs logging
*******************************************************

.. topic:: Specification scope and status

   This specification provides a partial overview of the current implementation.

Motivation
==========

This specification delineates the applicable contexts for using
:ref:`result records <chap_design_result_records>`, :ref:`exceptions <chap_design_exception_handling>`,
:ref:`progress reporting <chap_design_progress_reporting>`, specific :ref:`log levels <chap_design_log_levels>`,
or other types of user messaging processes.


Specification
=============

Result records
--------------

**Result records are the only return value format** for all DataLad interfaces.

Constrasting with classic Python interfaces that return specific non-annotated values,
DataLad interfaces implement message passing by yielding :ref:`result records <chap_design_result_records>`
that are associated with individual operations. Result records are routinely inspected throughout
the code base and their annotations are used to inform general program flow and error handling.

Command calls can include an ``on_failure`` parameterization to specify how to
proceed with a particular operation if a returned result record is
:ref:`classified as a failure result <target-result-status>`. Command calls can
also include a ``result_renderer`` parameterization to explicitly enable or
disable the handling and rendering of result records.

Developers should be aware that external callers will use command call parameterizations
that can selectively ignore or act on result records, and that the process should therefore
yield meaningful result records. If, in turn, the process itself receives a set of result
records from a sub-process, these should be inspected individually in order to identify result
values that could require re-annotation or status re-classification.


Exception handling
------------------

In general, **exceptions should be raised when there is no way to ignore or recover from
the offending action**.

More specifically, raise an exception when:

1. A DataLad interface's parameter specifications are violated
2. An additional requirement (beyond parameters) for the successful running of a
   command, function, or process is not met

It must be made clear to the user/caller what the exact cause of the exception
is, given the context within which the user/caller triggered the action.
This is achieved directly via a (re)raised exception, as opposed to logging messages or
results records which could be ignored or unseen by the user.

.. note::
   In the case of a complex set of dependent actions it could be expensive to
   confirm parameter violations. In such cases, initial sub-processes might already generate
   result records that have to be inspected by the caller, and it could be practically better
   to yield a result record (with ``status=[error|impossible]``) to communicate the failure.
   It would then be up to the upstream caller to decide whether to specify
   ``on_failure='ignore'`` or whether to inspect individual result records and turn them
   into exceptions or not.


Logging
-------

Logging provides developers with additional means to describe steps in a process,
so as to **allow insight into the program flow during debugging** or analysis of e.g.
usage patterns. Logging can be turned off externally, filtered, and redirected. Apart from
the :ref:`log-level <chap_design_log_levels>` and message, it is not inspectable and
cannot be used to control the logic or flow of a program.

Importantly, logging should not be the primary user messaging method for command outcomes,
Therefore:

1. No command should rely solely on logging for user communication
2. Use logging for in-progress user communication via the mechanism for :ref:`progress reporting <chap_design_progress_reporting>`
3. Use logging to inform debugging processes


UI Module
---------

The :mod:`~datalad.ui` module provides the means to communicate information
to the user in a user-interface-specific manner, e.g. via a console, dialog, or an iPython interface.
Internally, all DataLad results processed by the result renderer are passed through the UI module.

Therefore: in cases where existing user communication processes are not appropriate,
developers should let explicit user communication happen through the UI module
as it provides the flexibility to adjust to the present UI. Specifically,
:py:func:`datalad.ui.message` allows passing a simple message via the UI module.


Examples
========

.. note::
   TODO