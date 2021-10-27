import logging
import os
import threading
from abc import ABCMeta
from enum import Enum
from queue import (
    Empty,
    Full,
    Queue,
)
from typing import (
    Any,
    IO,
    Optional,
    Tuple,
    Union,
)


lgr = logging.getLogger("datalad.runner.runnerthreads")


class IOState(Enum):
    ok = "ok"
    timeout = "timeout"


class ExitingThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.exit_requested = False

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the instance has to check for
        self.exit_requested and act accordingly. It might not
        do that.
        """
        self.exit_requested = True


class BlockingOSReaderThread(ExitingThread):
    """
    A blocking OS file reader. If it reads
    anything, it stores its data in a queue.
    That allows a consumer to block
    on OS-reads with timeout, independent from
    the OS read capabilities.
    It enqueues bytes if something is read. If
    the file is close, it will enqueue None and
    exit.
    """
    def __init__(self,
                 source: IO,
                 length: int = 1024,
                 ):

        super().__init__()
        self.source = source
        self.length = length
        self.queue = Queue(1)

    def run(self):

        lgr.log(5, "%s started", self)

        while not self.exit_requested:
            data = os.read(self.source.fileno(), self.length)
            if data == b"":
                self.queue.put(None)
                break
            if self.exit_requested:
                break

            self.queue.put(data)

        lgr.log(5, "%s exiting", self)


class BlockingOSWriterThread(ExitingThread):
    """
    A blocking OS file writer. It fetches
    data from the queue and writes it via
    OS-level write functions. The queue has
    size 1. That allows a producer to block
    on OS-writes with timeout, independent from
    the OS write capabilities.
    It expects bytes in the Queue or None.
    Bytes will be written, if None is fetched
    from the queue, the thread will exit.
    """
    def __init__(self,
                 destination: IO,
                 ):

        super().__init__()
        self.destination = destination
        self.queue = Queue(1)

    def run(self):

        lgr.log(5, "%s started", self)

        while not self.exit_requested:
            data = self.queue.get()
            if data is None:
                break

            written = 0
            while written < len(data) and not self.exit_requested:
                written += os.write(
                    self.destination.fileno(),
                    data[written:])

        lgr.log(5, "%s exiting", self)


class SignalingThread(ExitingThread, metaclass=ABCMeta):
    def __init__(self,
                 identifier: str,
                 signal_queue: Queue,
                 ):

        super().__init__()
        self.identifier = identifier
        self.signal_queue = signal_queue

    def signal(self,
               state: IOState,
               data: Union[bytes, None]):
        self.signal_queue.put((self.identifier, state, data))


class ReadThread(SignalingThread):
    def __init__(self,
                 identifier: Any,
                 source_blocking_queue: Queue,
                 destination_queue: Queue,
                 signal_queue: Queue,
                 timeout: Optional[float] = None,
                 ):

        super().__init__(identifier, signal_queue)
        self.source_blocking_queue = source_blocking_queue
        self.destination_queue = destination_queue
        self.timeout = timeout

    def read_blocking(self,
                      timeout: Optional[float] = None,
                      ) -> Tuple[IOState, Union[bytes, None]]:

        try:
            data = self.source_blocking_queue.get(block=True, timeout=timeout)
            return IOState.ok, data
        except Empty:
            return IOState.timeout, None

    def write(self,
              state: IOState,
              data: Union[bytes, None]):
        self.destination_queue.put((self.identifier, state, data))

    def signal(self,
               state: IOState,
               data: Union[bytes, None]):
        self.signal_queue.put((self.identifier, state, data))

    def run(self):

        lgr.log(5, "%s started", self)

        # Get data from source queue until exit is requested.
        data = None
        while not self.exit_requested:

            # Get data or timeout until exit is requested.
            while not self.exit_requested:
                state, data = self.read_blocking(self.timeout)
                # On timeout, send timeout info to signal queue
                if state == IOState.ok:
                    break
                elif state == IOState.timeout:
                    self.signal(state, None)
                else:
                    raise RuntimeError(f"invalid IOState {state}")

            # If an exit was requested, exit from this thread
            # before trying to put data into the output queue.
            if self.exit_requested:
                break

            # If we received None, the source is closed,
            # send closed indicator to signal queue and exit
            # the thread.
            if data is None:
                self.signal(IOState.ok, None)
                break

            # We received proper date, enqueue
            # it to the destination queue
            self.write(IOState.ok, data)

        lgr.log(5, "%s exiting (last data was: %s)", self, data)


class WriteThread(SignalingThread):
    def __init__(self,
                 identifier: Any,
                 source_queue: Queue,
                 destination_blocking_queue: Queue,
                 signal_queue: Queue,
                 timeout: Optional[float] = None,
                 ):

        super().__init__(identifier, signal_queue)
        self.source_queue = source_queue
        self.destination_blocking_queue = destination_blocking_queue
        self.timeout = timeout

    def write_blocking(self,
                       data: bytes,
                       timeout: Optional[float] = None,
                       ) -> IOState:

        try:
            self.destination_blocking_queue.put(
                data, block=True, timeout=timeout)
            return IOState.ok
        except Full:
            return IOState.timeout

    def run(self):

        lgr.log(5, "%s started", self)

        # Get data from source queue until exit is requested.
        while not self.exit_requested:

            # Get data, if None was enqueued, the source wants
            # us to exit the thread.
            data = self.source_queue.get()
            if data is None:
                self.signal(IOState.ok, None)
                break

            # Received proper data, try to write it to
            # the destination queue.
            while not self.exit_requested:
                state = self.write_blocking(data, self.timeout)
                if state == IOState.ok:
                    break
                elif state == IOState.timeout:
                    self.signal(state, None)
                else:
                    raise RuntimeError(f"invalid IOState: {state}")

        lgr.log(5, "%s exiting", self)
