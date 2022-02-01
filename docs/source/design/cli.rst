.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_cli:

**********************
Command line interface
**********************

.. topic:: Specification scope and status

   This incomplete specification describes the current implementation.

The command line interface (CLI) implementation is located at ``datalad.cli``.
It provides a console entry point that automatically constructs an
``argparse``-based command line parser, which is used to make adequately
parameterized calls to the targeted command implementations. It also performs
error handling. The CLI automatically supports all commands, regardless of
whether they are provided by the core package, or by extensions. It only
requires them to be discoverable via the respective extension entry points,
and to implement the standard :class:`datalad.interface.base.Interface`.


Basic workflow of a command line based command execution
========================================================

The functionality of the main command line entrypoint described here is
implemented in ``datalad.cli.main``.

1. Construct an ``argparse`` parser.

   - this is happening with inspection of the actual command line arguments
     in order to avoid needless processing

   - when insufficient arguments or other errors are detected, the CLI will
     fail informatively already at this stage

2. Detect argument completions events, and utilize the parser in a optimized
   fashion for this purpose.

3. Determine the to-be-executed command from the given command line arguments.

4. Read any configuration overrides from the command line arguments.

5. Change the process working directory, if requested.

6. Execute the target command in one of two modes:

   a. With a basic exception handler

   b. With an exception hook setup that enables dropping into a debugger
      for any exception that reaches the command line ``main()`` routine.

7. Unless a debugger is utilized, five error categories are distinguished
   (in the order given below):

   1. Insufficient arguments (exit code 2)

      A command was called with inadequate or incomplete parameters.

   2. Incomplete results (exit code 1)

      While processing an error occurred.

   3. A specific internal shell command execution failed (exit code relayed
      from underlying command)

      The error is reported, as if the command would have been executed
      directly in the command line. Its output is written to the ``stdout``,
      ``stderr`` streams, and the exit code of the DataLad process matches
      the exit code of the underlying command.

   4. Keyboard interrupt (exit code 3)

      The process was interrupted by the equivalent of a user hitting
      ``Ctrl+C``.

   5. Any other error/exception.


Command parser construction by ``Interface`` inspection
=======================================================

The parser setup described here is implemented in ``datalad.cli.parser``.

A dedicated sub-parser for any relevant DataLad command is constructed. For
normal execution use cases, only a single subparser for the target command
will be constructed for speed reasons. However, when the command line help
system is requested (``--help``) subparsers for all commands (including
extensions) are constructed. This can take a considerable amount of time
that grows with the number of installed extensions.

The information necessary to configure a subparser for a DataLad command is
determined by inspecting the respective
:class:`~datalad.interface.base.Interface` class for that command, and reusing
individual components for the parser. This includes:

- the class docstring

- a ``_params_`` member with a dict of parameter definitions

- a ``_examples_`` member, with a list of example definitions

All docstrings used for the parser setup will be processed by applying a
set of rules to make them more suitable for the command line environment.
This includes the processing of ``CMD`` markup macros, and stripping their
``PYTHON`` counter parts. Parameter constraint definition descriptions
are also altered to exclude Python-specific idioms that have no relevance
on the command line (e.g., the specification of ``None`` as a default).


CLI-based execution of ``Interface`` command
============================================

The execution handler described here is implemented in ``datalad.cli.exec``.

Once the main command line entry point determine that a command shall be
executed, it triggers a handler function that was assigned and parameterized
with the underlying command :class:`~datalad.interface.base.Interface` during
parser construction. At the time of execution, this handler is given the result
of ``argparse``-based command line argument parsing (i.e., a ``Namespace``
instance).

From this parser result, the handler constructs positional and keyword
arguments for the respective ``Interface.__call__()`` execution. It does
not only process command-specific arguments, but also generic arguments,
such as those for result filtering and rendering, which influence the central
processing of result recorded yielded by a command.

If an underlying command returns a Python generator it is unwound to trigger
the respective underlying processing. The handler performs no error handling.
This is left to the main command line entry point.

