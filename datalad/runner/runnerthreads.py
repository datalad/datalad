import logging
import os
import threading
from abc import (
    abstractmethod,
    ABCMeta,
)
from enum import Enum
from queue import (
    Empty,
    Full,
    Queue,
)
from typing import (
    Any,
    IO,
    List,
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
            try:
                data = os.read(self.source.fileno(), self.length)
            except (ValueError, OSError):
                # The source was most likely closed, indicate EOF.
                data = b""

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
            if isinstance(data, tuple):
                identifier, state, data = data
            if data is None:
                self.destination.close()
                break

            try:
                written = 0
                while written < len(data) and not self.exit_requested:
                    written += os.write(
                        self.destination.fileno(),
                        data[written:])
            except (BrokenPipeError, OSError, ValueError):
                # The destination was most likely closed, indicate EOF.
                self.queue.put(None)
                break

        lgr.log(5, "%s exiting", self)


class TransportThread(ExitingThread, metaclass=ABCMeta):
    def __init__(self,
                 identifier: str,
                 signal_queues: List[Queue],
                 timeout: Optional[float] = None
                 ):

        super().__init__()
        self.identifier = identifier
        self.signal_queues = signal_queues
        self.timeout = timeout

    def signal(self,
               state: IOState,
               data: Union[bytes, None]):
        for queue in self.signal_queues:
            # Ensure that self.signal() will never block.
            # TODO: separate the timeout and EOF signal paths?
            try:
                queue.put((self.identifier, state, data), block=True, timeout=1)
            except Full:
                lgr.debug(
                    f"timeout while trying to signal "
                    f"{(self.identifier, state, data)}")

    @abstractmethod
    def read(self,
             timeout: Optional[float] = None,
             ) -> Tuple[IOState, Union[bytes, None]]:
        raise NotImplementedError

    @abstractmethod
    def write(self,
              data: Union[bytes, None],
              timeout: Optional[float] = None
              ) -> IOState:
        raise NotImplementedError

    def run(self):

        lgr.log(5, "%s (%s) started", self, self.identifier)

        # Copy data from source queue to destination queue
        # until exit is requested. If timeouts arise, signal
        # them to the receiver via the signal queue.
        while not self.exit_requested:

            # Get data until exit is requested, use timeout
            # to implement exit checks.
            while not self.exit_requested:

                state, data = self.read(self.timeout)
                if state == IOState.timeout:
                    # On timeout, send timeout info to signal queues
                    self.signal(state, None)
                    continue

                assert state == IOState.ok
                break

            # If the source sends None-data it wants
            # us to exit the thread. Signal this to
            # the signal queues (which might or might
            # not be contain the output queue),
            # and exit the thread
            if data is None:
                self.signal(IOState.ok, None)
                break

            while not self.exit_requested:
                state = self.write(data, self.timeout)
                if state == IOState.timeout:
                    # On timeout, send timeout info to signal queue
                    self.signal(state, None)
                    continue

                assert state == IOState.ok
                break

        lgr.log(
            5,
            "%s exiting (exit_requested: %s, last data: %s)",
            self,
            self.exit_requested, data)


class ReadThread(TransportThread):
    def __init__(self,
                 identifier: Any,
                 source_blocking_queue: Queue,
                 destination_queue: Queue,
                 signal_queues: List[Queue],
                 timeout: Optional[float] = None,
                 ):

        super().__init__(identifier, signal_queues)
        self.source_blocking_queue = source_blocking_queue
        self.destination_queue = destination_queue
        self.timeout = timeout

    def read(self,
             timeout: Optional[float] = None,
             ) -> Tuple[IOState, Union[bytes, None]]:

        try:
            data = self.source_blocking_queue.get(block=True, timeout=timeout)
            return IOState.ok, data
        except Empty:
            return IOState.timeout, None

    def write(self,
              data: Union[bytes, None],
              timeout: Optional[float] = None
              ) -> IOState:

        # We write to an unlimited queue, no need for timeout checking.
        self.destination_queue.put((self.identifier, IOState.ok, data))
        return IOState.ok


class WriteThread(TransportThread):
    def __init__(self,
                 identifier: Any,
                 source_queue: Queue,
                 destination_blocking_queue: Queue,
                 signal_queues: List[Queue],
                 timeout: Optional[float] = None,
                 ):

        super().__init__(identifier, signal_queues)
        self.source_queue = source_queue
        self.destination_blocking_queue = destination_blocking_queue
        self.timeout = timeout

    def read(self,
             timeout: Optional[float] = None,
             ) -> Tuple[IOState, Union[bytes, None]]:
        return IOState.ok, self.source_queue.get()

    def write(self,
              data: bytes,
              timeout: Optional[float] = None,
              ) -> IOState:
        try:
            self.destination_blocking_queue.put(
                data, block=True, timeout=timeout)
            return IOState.ok
        except Full:
            return IOState.timeout
