.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_threaded_runner:


****************
Threaded runner
****************

.. topic:: Specification scope and status

   This specification provides an overview over the current implementation.


Datalad often requires the execution of subprocesses. While subprocesses are executed, datalad, i.e. its main thread, should be able to read data from stdout and stderr of the subprocess as well as write data to stdin of the subprocess. This requires a way to efficiently multiplex reading from stdout and stderr of the subprocess as well as writing to stdin of the subprocess.

Since non-blocking IO and waiting on multiple sources (poll or select) differs wastly in terms of capabilities and API on different OSs, we decided to use blocking IO and threads to multiplex reading from different sources.

Generally we have a number of threads. Each thread can read from either a single queue or a file descriptor. Reading is done blocking. Each thread can put data into multiple queues. This is used to transport data that was read as well as for signaling conditions like closed file descriptors.

Conceptually, there are three layers of threads:

 - layer 1: main thread
 - layer 2: transport threads (1 per process I/O descriptor)
 - layer 3: blocking OS reading/writing threads (1 per process I/O descriptor)

Besides the main thread, there are two additional threads for stdin, for stdout, and for stderr capture. One of those threads reads from or writes to a file desriptor in a tight loop. It will exit if either the file descriptor is closed, if an error occurs on reading, if get() on the input queue yields `None`, or if an exit was requested by `thread.request_exit()` and the thread is unblocked on read/write/get(). Threads put data either in infinite queues or in finite queues if it takes no longer than 1 second.

The blocking OS threads in layer 3 are mainly used to enable timeouts of all operations in threads of layer 2.

