.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_batched_command:

*******************************
BatchedCommand and BatchedAnnex
*******************************

.. topic:: Specification scope and status

   This specification describes the implementation of ``BatchedCommand`` and
   ``BatchedAnnex`` in ``datalad`` version <= 0.15.x of datalad.


Batched Command
===============

The class ``BatchedCommand`` (in ``datalad.cmd``), holds an instance of a running subprocess, allows to send commands to the subprocess over its stdin, and to receive subprocess responses over its stdout.

Commands can be provided to an instance of ``BatchedCommand`` by passing a single command or a list of commands to ``BatchCommand.__call__()``, i.e. apply the function call-operator to an instance of ``BatchedCommand``. A command is either a string or a tuple of strings. In the latter case, the elements of the tuple will be joined by ``" "``. More than one command can be given by providing a list of commands, i.e. a list of strings or tuples.

``BatchedCommand`` will send each command sent to the subprocess in a single line, terminated by ``"\n"``. After the command is sent, ``BatchedCommand`` calls an output-handler with stdout of the subprocess as argument. The output handler can be provided to the constructor. If no output handler is provided, a default output-handler is used. The default output-handler reads a single output line on stdout, using ``io.IOBase.readline()``, and returns the ``rstrip()``-ed line.

The subprocess must at least emit one line of output per line of input in order to prevent the calling thread from blocking. In addition, the size of the output, i.e. the number of lines that the result consists of, must be discernible by the processor. The subprocess must either return a fixed number of lines per input line, or it must indicate the end of a result in some other way, e.g. with an empty line.

Remark: In principle any output processing could be performed. But, if the output processor blocks on stdout, the calling thread will be blocked. In reality the fixed arguments that ``BatchedCommand`` provides to the Popen-constructor, i.e. ``bufsize=1`` and ``universal_newlines=True``, lead to line-based text processing in the output-handler. With the line-based command provision in addition, ``BatchedCommand`` is geared towards supporting the batch processing modes of ``git`` and ``git-annex``. *This has to be taken into account when providing a custom output handler.*

Remark 2: Although the default output handler, i.e. ``datalad.cmd.readline_stripped``, is deprecated, it is used by ``BatchedCommand``. It is not clear which alternative should be provided. Although, there is documentation (besides the source and this document) that mentions that stdout is line-buffered, and in text mode. This configuration would make it difficult (impossible) to use BatchedCommand to communicate with a subprocess that does not output line-breaks.

When ``BatchedCommand.close()`` is called, stdin of the subprocess is closed. This indicates the end of processing to the subprocess. Generally the subprocess is expected to exit shortly after that. Stderr of the subprocess is redirected to a temporary file which is read when ``BatchedCommand.close()`` is called. Its content will be returnd by ``BatchCommand.close()`` if the parameter ``return_stderr`` is ``True``.

Implementation details
......................

``BatchedCommand`` uses ``subprocess.Popen`` directly. It constructs a ``Popen``-object with ``universal_newlines=True``, forcing stdin and stdout of the subprocess to text mode. It uses ``bufsize=1`` to enable line-buffering, allowing the output handler to use ``readline()`` and the stdout of the subprocess to fetch a single response line.

``BatchedCommand`` has a restart capability. If the subprocess exited, another process with the identical command line is started. (No state is transferred from the old process though)

``BatchedCommand.close()`` queries the configuration to determine how to handle non-exiting processes (there is no killing, processes or process zombies might just linger around until the next reboot).

``BatchedCommand`` can process a list of multiple commands at once, but it will collect all answers before returning a result. That means, if you send 1000 commands, ``BatchedCommand`` will return after having received 1000 responses.


BatchedAnnex
============
``BatchedAnnex`` is a subclass of ``BatchedCommand`` (which it actually doesn't have to be, it just adds git-annex specific parameters to the command and sets a specific output handler).

``BatchedAnnex`` provides a new output-handler if the constructor-argument ``json`` is ``True``. In this case, an output handler is used that reads a single line from stdout, strips the line and converts it into a json object, which is returned. If the stripped line is empty, an empty dictionary is returned.
