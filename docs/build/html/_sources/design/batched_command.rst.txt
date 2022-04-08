.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_batched_command:

*******************************
BatchedCommand and BatchedAnnex
*******************************

.. topic:: Specification scope and status

   This specification describes the new implementation of ``BatchedCommand`` and
   ``BatchedAnnex`` in ``datalad``.


Batched Command
===============

The class ``BatchedCommand`` (in ``datalad.cmd``), holds an instance of a running subprocess, allows to send requests to the subprocess over its stdin, and to receive responses from the subprocess over its stdout.

Requests can be provided to an instance of ``BatchedCommand`` by passing a single request or a list of requests to ``BatchCommand.__call__()``, i.e. by applying the function call-operator to an instance of ``BatchedCommand``. A request is either a string or a tuple of strings. In the latter case, the elements of the tuple will be joined by ``" "``. More than one request can be given by providing a list of requests, i.e. a list of strings or tuples. In this case, the return value will be a list with one response for every request.

``BatchedCommand`` will send each request that is sent to the subprocess as a single line, after terminating the line by ``"\n"``. After the request is sent, ``BatchedCommand`` calls an output-handler with stdout-ish (an object that provides a ``readline()``-function which operates on the stdout of the subprocess) of the subprocess as argument. The output-handler can be provided to the constructor. If no output-handler is provided, a default output-handler is used. The default output-handler reads a single output line on stdout, using ``io.IOBase.readline()``, and returns the ``rstrip()``-ed line.

The subprocess must at least emit one line of output per line of input in order to prevent the calling thread from blocking. In addition, the size of the output, i.e. the number of lines that the result consists of, must be discernible by the output-handler. That means, the subprocess must either return a fixed number of lines per input line, or it must indicate the end of a result in some other way, e.g. with an empty line.

Remark: In principle any output processing could be performed. But, if the output-handler blocks on stdout, the calling thread will be blocked. Due to the limited capabilities of the stdout-ish that is passed to the output-handler, the output-handler must rely on ``readline()`` to process the output of the subprocess. Together with the line-based request sending, ``BatchedCommand`` is geared towards supporting the batch processing modes of ``git`` and ``git-annex``. *This has to be taken into account when providing a custom output handler.*

When ``BatchedCommand.close()`` is called, stdin, stdout, and stderr of the subprocess are closed. This indicates the end of processing to the subprocess. Generally the subprocess is expected to exit shortly after that. ``BatchedCommand.close()`` will wait for the subprocess to end, if the configuration ``datalad.runtime.stalled-external`` is set to ``"wait"``. If the configuration ``datalad.runtime.stalled-external`` is set to ``"abandon"``, ``BatchedCommand.close()`` will return after "timeout" seconds if ``timeout`` was provided to ``BatchedCommand.__init__()``, otherwise it will return after 11 seconds. If a timeout occurred, the attribute ``wait_timed_out`` of the ``BatchedCommand`` instance will be set to ``True``. If ``exception_on_timeout=True`` is provided to ``BatchedCommand.__init__()``, a ``subprocess.TimeoutExpired`` exception will be raised on a timeout while waiting for the process. It is not safe to reused a ``BatchedCommand`` instance after such an exception was risen.

Stderr of the subprocess is gathered in a byte-string. Its content will be returned by ``BatchCommand.close()`` if the parameter ``return_stderr`` is ``True``.


Implementation details
......................

``BatchedCommand`` uses ``WitlessRunner`` with a protocol that has ``datalad.runner.protocol.GeneratorMixIn`` as a super-class. The protocol uses an output-handler to process data, if an output-handler was specified during construction of ``BatchedCommand``.

``BatchedCommand.close()`` queries the configuration key ``datalad.runtime.stalled-external`` to determine how to handle non-exiting processes (there is no killing, processes or process zombies might just linger around until the next reboot).

The current implementation of ``BatchedCommand`` can process a list of multiple requests at once, but it will collect all answers before returning a result. That means, if you send 1000 requests, ``BatchedCommand`` will return after having received 1000 responses.


BatchedAnnex
============
``BatchedAnnex`` is a subclass of ``BatchedCommand`` (which it actually doesn't have to be, it just adds git-annex specific parameters to the command and sets a specific output handler).

``BatchedAnnex`` provides a new output-handler if the constructor-argument ``json`` is ``True``. In this case, an output handler is used that reads a single line from stdout, strips the line and converts it into a json object, which is returned. If the stripped line is empty, an empty dictionary is returned.
