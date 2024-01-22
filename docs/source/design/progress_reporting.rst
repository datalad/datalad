.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_progress_reporting:

******************
Progress reporting
******************

.. topic:: Specification scope and status

   This specification describes the current implementation.


Progress reporting is implemented via the logging system. A dedicated function
:py:func:`datalad.log.log_progress` represents the main API for progress
reporting. For some standard use cases, the utilities
:py:func:`datalad.log.with_progress` and
:py:func:`datalad.log.with_result_progress` can simplify result reporting
further.


Design and implementation
=========================

This basic idea is to use an instance of datalad's loggers to emit log messages
with particular attributes that are picked up by
:py:class:`datalad.log.ProgressHandler` (derived from
:py:class:`logging.Handler`), and are acted on differently, depending on
configuration and conditions of a session (e.g., interactive terminal sessions
vs.  non-interactive usage in scripts). This variable behavior is implemented
via the use of :py:mod:`logging` standard library log filters and handlers.
Roughly speaking, :py:class:`datalad.log.ProgressHandler` will only be used for
interactive sessions. In non-interactive cases, progress log messages are
inspected by :py:func:`datalad.log.filter_noninteractive_progress`, and are
either discarded or treated like any other log message (see
:py:meth:`datalad.log.LoggerHelper.get_initialized_logger` for details on the
handler and filter setup).

:py:class:`datalad.log.ProgressHandler` inspects incoming log records for
attributes with names starting with `dlm_progress`. It will only process such
records and pass others on to the underlying original log handler otherwise.

:py:class:`datalad.log.ProgressHandler` takes care of creating, updating and
destroying any number of simultaneously running progress bars. Progress reports
must identify the respective process via an arbitrary string ID. It is the
caller's responsibility to ensure that this ID is unique to the target
process/activity.


Reporting progress with `log_progress()`
========================================

Typical progress reporting via :py:func:`datalad.log.log_progress` involves
three types of calls.

1. Start reporting progress about a process
-------------------------------------------

A typical call to start of progress reporting looks like this

.. code-block:: python

    log_progress(
        # the callable used to emit log messages
        lgr.info,
        # a unique identifiers of the activity progress is reported for
        identifier,
        # main message
        'Unlocking files',
        # optional unit string for a progress bar
        unit=' Files',
        # optional label to be displayed in a progress bar
        label='Unlocking',
        # maximum value for a progress bar
        total=nfiles,
    )

A new progress bar will be created automatically for any report with a previously
unseen activity ``identifier``. It can be configured via the specification of
a number of arguments, most notably a target ``total`` for the progress bar.
See :py:func:`datalad.log.log_progress` for a complete overview.

Starting a progress report must be done with a dedicated call. It cannot be combined
with a progress update.


2. Update progress information about a process
----------------------------------------------

Any subsequent call to :py:func:`datalad.log.log_progress` with an activity
identifier that has already been seen either updates, or finishes the progress
reporting for an activity. Updates must contain an ``update`` key which either
specifies a new value (if `increment=False`, the default) or an increment to
previously known value (if `increment=True`):

.. code-block:: python

    log_progress(
        lgr.info,
        # must match the identifier used to start the progress reporting
        identifier,
        # arbitrary message content, string expansion supported just like
        # regular log messages
        "Files to unlock %i", nfiles,
        # critical key for report updates
        update=1,
        # ``update`` could be an absolute value or an increment
        increment=True
    )

Updating a progress report can only be done after a progress reporting was
initialized (see above).


3. Report completion of a process
---------------------------------

A progress bar will remain active until it is explicitly taken down, even if an
initially declared ``total`` value may have been reached. Finishing a progress
report requires a final log message with the corresponding identifiers which,
like the first initializing message, does NOT contain an ``update`` key.

.. code-block:: python

    log_progress(
        lgr.info,
        identifier,
        # closing log message
        "Completed unlocking files",
    )


Progress reporting in non-interactive sessions
----------------------------------------------

:py:func:`datalad.log.log_progress` takes a `noninteractive_level` argument
that can be used to specify a log level at which progress is logged when no
progress bars can be used, but actual log messages are produced.

.. code-block:: python

    import logging

    log_progress(
        lgr.info,
        identifier,
        "Completed unlocking files",
        noninteractive_level=logging.INFO
    )

Each call to :py:func:`~datalad.log.log_progress` can be given a different
log level, in order to control the verbosity of the reporting in such a scenario.
For example, it is possible to log the start or end of an activity at a higher
level than intermediate updates. It is also possible to single out particular
intermediate events, and report them at a higher level.

If no `noninteractive_level` is specified, the progress update is unconditionally
logged at the level implied by the given logger callable. 


Reporting progress with `with_(result_)progress()`
==================================================

For cases were a list of items needs to be processes sequentially, and progress
shall be communicated, two additional helpers could be used: the decorators
:py:func:`datalad.log.with_progress` and
:py:func:`datalad.log.with_result_progress`. They require a callable that takes
a list (or more generally a sequence) of items to be processed as the first
positional argument. They both set up and perform all necessary calls to
:py:func:`~datalad.log.log_progress`.

The difference between these helpers is that
:py:func:`datalad.log.with_result_progress` expects a callable to produce
DataLad result records, and supports customs filters to decide which particular
result records to consider for progress reporting (e.g., only records for a
particular `action` and `type`).


Output non-progress information without interfering with progress bars
======================================================================

:py:func:`~datalad.log.log_progress` can also be useful when not reporting
progress, but ensuring that no other output is interfering with progress bars,
and vice versa. The argument `maint` can be used in this case, with no
particular activity identifier (it always impacts all active progress bars):


.. code-block:: python

    log_progress(
        lgr.info,
        None,
        'Clear progress bars',
        maint='clear',
    )


This call will trigger a temporary discontinuation of any progress bar display.
Progress bars can either be re-enabled all at once, by an analog message with
``maint='refresh'``, or will re-show themselves automatically when the next
update is received. A :py:func:`~datalad.log.no_progress` context manager helper
can be used to surround your context with those two calls to prevent progress
bars from interfering.
