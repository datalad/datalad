.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_exception_handling:

******************
Exception handling
******************

.. topic:: Specification scope and status

   This specification describes the current implementation target.


Catching exceptions
===================

Whenever we catch an exception in an ``except`` clause, the following rules
apply:

- unless we (re-)raise, the first line instantiates a
  :class:`~datalad.support.exceptions.CapturedException`::

      except Exception as e:
          ce = CapturedException(e)

  First, this ensures a low-level (8) log entry including the traceback of that
  exception. The depth of the included traceback can be limited by setting the
  ``datalad.exc.str.tb_limit`` config accordingly.

  Second, it deletes the frame stack references of the exception and keeps
  textual information only, in order to avoid circular references, where an
  object (whose method raised the exception) isn't going to be picked by the
  garbage collection. This can be particularly troublesome if that object holds
  a reference to a subprocess for example. However, it's not easy to see in what
  situation this would really be needed and we never need anything other than
  the textual information about what happened. Making the reference cleaning a
  general rule is easiest to write, maintain and review.

- if we raise, neither a log entry nor such a
  :class:`~datalad.support.exceptions.CapturedException` instance is to be
  created.
  Eventually, there will be a spot where that (re-)raised exception is caught.
  This then is the right place to log it. That log entry will have the
  traceback, there's no need to leave a trace by means of log messages!

- if we raise, but do not simply reraise that exact same exception, in order to
  change the exception class and/or its message, ``raise from`` must be used!::

      except SomeError as e:
          raise NewError("new message") from e

  This ensures that the original exception is properly registered as the cause
  for the exception via its ``__cause__`` attribute. Hence, the original
  exception's traceback will be part of the later on logged traceback of the new
  exception.


Messaging about an exception
============================

In addition to the auto-generated low-level log entry there might be a need to
create a higher-level log, a user message or a (result) dictionary that includes
information from that exception. While such messaging may use anything the
(captured) exception provides, please consider that "technical" details about an
exception are already auto-logged and generally not incredibly meaningful for
users.

For message creation :class:`~datalad.support.exceptions.CapturedException`
comes with a couple of ``format_*`` helper methods, its ``__str__`` provides a
short representation of the form ``ExceptionClass(message)`` and its
``__repr__`` the log form with a traceback tht is used for the auto-generated
log.

For result dictionaries :class:`~datalad.support.exceptions.CapturedException`
can be assigned to the field ``exception``. Currently, ``get_status_dict`` will
consider this field and create an additional field with a traceback string.
Hence, whether putting a captured exception into that field actually has an
effect depends on whether ``get_status_dict`` is subsequently used with that
dictionary. In the future such functionality may move into result renderers
instead, leaving the decision of what to do with the passed
:class:`~datalad.support.exceptions.CapturedException` to them. Therefore, even
if of no immediate effect, enhancing the result dicts accordingly makes sense
already, since it may be useful when using datalad via its python interface
already and provide instant benefits whenever the result rendering gets such an
upgrade.
