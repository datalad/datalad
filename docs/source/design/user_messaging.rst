.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_user_messaging:

*******************************************************
User messaging: result records vs exceptions vs logging
*******************************************************

.. topic:: Specification scope and status

   This specification aims to delineate the applicable contexts for using result records,
   exceptions, logging, or other types of user messaging methods.

Motivation
==========

Design specifications exist for :ref:`chap_design_result_records`,
:ref:`chap_design_exception_handling`, :ref:`chap_design_log_levels`, and 
:ref:`chap_design_progress_reporting`, and an ideal yet elusive goal is the consistent
application of these methods in the applicable contexts. 

From a **developer's perspective**, a specification for the proper use of specific user
messaging methods creates a best practice standard that simplifies the implementation
process, minimizes code duplication, and ensures consistency in the code base. This
applies both to development in DataLad core as well as in DataLad extensions.

From a **user's perspective**, it is imperative to receive the most appropriate and
unambiguous message relating to the current context or action.

Discrepancies (on the development side) and resulting ambiguity (on the user side) arise
when the chosen user messaging methods are implemented interchangeably, inconsistently,
within contexts that do not warrant them, and in ways that do not inform users
appropriately.

Consequently, the motivation of this specification is to delineate the applicable
contexts for using result records, exceptions, logging, or other types of
user messaging processes.


Specification
=============

Result records
--------------

**Result records are the standard and preferred return value** format for all
DataLad commands. Result records are routinely inspected throughout the code base,
and are used to inform generic error handling, as well as particular calling commands
on how to proceed with a specific operation.

Yield result records when:

1. A generic and standard way of error handling is considered useful
2. A process can reasonably be continued despite evident errors or shortcomings in
   its subprocesses

Based on the ``status`` field of a result record, a result is categorized into
*success* (``ok``, ``notneeded``) and *failure* (``impossible``, ``error``).
Depending on the ``on_failure`` parameterization of a command call (``on_failure='stop'``,
``on_failure='continue'``, or ``on_failure='ignore'``), any failure-result
emitted by a command can lead to an ``IncompleteResultsError`` being raised on command
exit, or a non-zero exit code on the command line.


Exception handling
------------------

In general, **exceptions should be raised when there is no way to ignore or recover from
the offending action**.

More specifically, raise an exception when:

1. A command's parameter specifications are violated
2. An additional requirement (beyond parameters) for the successful running of a
   command, function, or process is not met

It must be made clear to the user/caller what the exact cause of the exception
is, given the context within which the user/caller triggered the action.
This is achieved directly via a (re)raised exception, as opposed to logging messages or
results records which could be ignored or unseen by the user.

If the relevant caller receives a set of result records, these should be inspected
individually in order to identify result status values that could require an exception
to be raised to the user/caller. Depending on developer-defined logic, an exception can
then be raised with an unambiguous message that excludes internal and intermediate
result messages.

Additionally, in the case of a complex set of dependent actions it could be expensive to
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
the log-level and message, it is not inspectable and cannot be used to control the logic
or flow of a program.

Importantly, logging is not a user messaging method. Therefore:

1. No command should rely on logging for user communication.


UI Module
---------

.. note::
   TODO



Examples
========

.. note::
   TODO