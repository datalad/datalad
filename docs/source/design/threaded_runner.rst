.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_threaded_runner:


****************
Threaded runner
****************

.. topic:: Specification scope and status

   This specification provides an overview over the current implementation.

Threads
=======

Datalad often requires the execution of subprocesses. While subprocesses are executed, datalad, i.e. its main thread, should be able to read data from stdout and stderr of the subprocess as well as write data to stdin of the subprocess. This requires a way to efficiently multiplex reading from stdout and stderr of the subprocess as well as writing to stdin of the subprocess.

Since non-blocking IO and waiting on multiple sources (poll or select) differs vastly in terms of capabilities and API on different OSs, we decided to use blocking IO and threads to multiplex reading from different sources.

Generally we have a number of threads. Each thread can read from either a single queue or a file descriptor. Reading is done blocking. Each thread can put data into multiple queues. This is used to transport data that was read as well as for signaling conditions like closed file descriptors.

Conceptually, there are three layers of threads:

 - layer 1: main thread
 - layer 2: transport threads (1 per process I/O descriptor)
 - layer 3: blocking OS reading/writing threads (1 per process I/O descriptor)

Besides the main thread, there are two additional threads for stdin, for stdout, and for stderr capture. One of those threads reads from or writes to a file desriptor in a tight loop. It will exit if either the file descriptor is closed, if an error occurs on reading, if get() on the input queue yields `None`, or if an exit was requested by `thread.request_exit()` and the thread is unblocked on read/write/get(). Threads put data either in infinite queues or in finite queues if it takes no longer than 1 second.

The blocking OS threads in layer 3 are mainly used to enable timeouts of all operations in threads of layer 2.

The main thread waits on the `output_queue`, into which the other threads feed directly or indirectly.


Protocols
=========

Due to its history the runner implementation uses the interface of the `SubprocessProtocol` (asyncio.protocols.SubprocessProtocol). Although the sub process protocol interface is defined in the asyncio libraries, the current thread-runner implementation does not make use of `async`.

    - `SubprocessProtocol.pipe_data_received(fd, data)`
    - `SubprocessProtocol.pipe_connection_lost(fd, exc)`
    - `SubprocessProtocol.process_exited()`

In addition the methods of `BaseProtocol` are called, i.e.:

    - `BaseProtocol.connection_made(transport)`
    - `BaseProtocol.connection_lost(exc)`


The datalad-provided protocol `WitlessProtocol` provides an additional callback:

    - `WitlessProtocol.timeout(fd)`

The method `timeout()` will be called when the parameter `timeout` in `WitlessRunner.run`, `ThreadedRunner.run`, or `run_command` is set to a number specifying the desired timeout in seconds. If no data is received from `stdin`, or `stderr` (if those are supposed to be captured) and no data could be written to `stdin` in the given timeout period, the method `WitlessProtocol.timeout(fd)` is called with `fd` set to the respective file number, e.g. 0, 1, or 2. If `WitlessProtocol.timeout(fd)` returns `True`, the file descriptor will be closed and the associated threads will exit.

The method `WitlessProtocol.timeout(fd)` is also called if all of stdout, stderr and stdin are closed and the process does not exit within the given interval. In this case `fd` is set to `None`. If `WitlessProtocol.timeout(fd)` returns `True` the process is terminated.


Object and Generator Results
================================

If the protocol that is provided to `run()` does not inherit `datalad.runner.protocol.GeneratorMixIn`, the final result that will be returned to the caller is determined by calling `WitlessProtocol._prepare_result()`. Whatever object this method returns will be returned to the caller.

If the protocol that is provided to `run()` does inherit `datalad.runner.protocol.GeneratorMixIn`, `run()` will return a `Generator`. This generator will yield the elements that were sent to it in the protocol-implementation by calling `GeneratorMixIn.send_result()` in the order in which the method `GeneratorMixIn.send_result()` is called. For example, if `GeneratorMixIn.send_result(43)` is called, the generator will yield `43`, and if `GeneratorMixIn.send_result({"a": 123, "b": "some data"})` is called, the generator will yield `{"a": 123, "b": "some data"}`.

Internally the generator is implemented by keeping track of the process state and waiting in the `output_queue` once, when `send` is called on it.
