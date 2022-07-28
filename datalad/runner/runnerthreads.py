from __future__ import annotations

import logging
import os
import threading
from abc import (
    abstractmethod,
    ABCMeta,
)
from enum import Enum
from queue import (
    Full,
    Queue,
)
from subprocess import Popen
from typing import (
    Any,
    IO,
    Optional,
)


lgr = logging.getLogger("datalad.runner.runnerthreads")


def _try_close(file_object: Optional[IO]):
    if file_object is not None:
        try:
            file_object.close()
        except OSError:
            pass


class IOState(Enum):
    ok = "ok"
    process_exit = "process_exit"


class SignalingThread(threading.Thread):
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue]
                 ):

        super().__init__(daemon=True)
        self.identifier = identifier
        self.signal_queues = signal_queues

    def __repr__(self):
        return f"Thread<{self.identifier}>"

    def __str__(self):
        return self.__repr__()

    def signal(self,
               content: Any
               ) -> bool:
        error_occurred = False
        for signal_queue in self.signal_queues:
            try:
                signal_queue.put(content, block=True, timeout=.1)
            except Full:
                lgr.debug("timeout while trying to signal: %s", content)
                error_occurred = True
        return not error_occurred


class WaitThread(SignalingThread):
    """
    Instances of this thread wait for a process to exit and enqueue
    an exit event in the signal queues.
    """
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue],
                 process: Popen
                 ):
        super().__init__(identifier, signal_queues)
        self.process = process

    def run(self) -> None:

        lgr.log(5, "%s (%s) started", self.identifier, self)

        self.process.wait()
        self.signal((self.identifier, IOState.process_exit, None))

        lgr.log(5, "%s (%s) exiting", self.identifier, self)


class ExitingThread(SignalingThread):
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue]
                 ):

        super().__init__(identifier, signal_queues)
        self.exit_requested = False

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the instance has to check for
        self.exit_requested and act accordingly. It might not
        do that.
        """
        self.exit_requested = True


class TransportThread(ExitingThread, metaclass=ABCMeta):
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue],
                 user_info: Any
                 ):

        super().__init__(identifier, signal_queues)
        self.user_info = user_info

    def __repr__(self) -> str:
        return f"Thread<({self.identifier}, {self.user_info})>"

    def __str__(self) -> str:
        return self.__repr__()

    def signal_event(self,
                     state: IOState,
                     data: Optional[bytes]
                     ) -> bool:
        return self.signal((self.user_info, state, data))

    @abstractmethod
    def read(self) -> Optional[bytes]:
        """
        Read data from source return None, if source is close,
        or destination close is required.
        """
        raise NotImplementedError

    @abstractmethod
    def write(self,
              data: bytes
              ) -> bool:
        """
        Write given data to destination, return True if data is
        written successfully, False otherwise.
        """
        raise NotImplementedError

    def run(self) -> None:

        lgr.log(5, "%s (%s) started", self.identifier, self)

        # Copy data from source queue to destination queue
        # until exit is requested. If timeouts arise, signal
        # them to the receiver via the signal queue.
        data: Optional[bytes] = b""
        while not self.exit_requested:

            data = self.read()
            # If the source sends None-data it wants
            # us to exit the thread. Signal this to
            # the downstream queues (which might or might
            # not be contain the output queue),
            # and exit the thread.
            if data is None:
                break

            if self.exit_requested:
                break

            succeeded = self.write(data)
            if not succeeded:
                break

        self.signal_event(IOState.ok, None)
        lgr.log(
            5,
            "%s (%s) exiting (exit_requested: %s, last data: %s)",
            self.identifier,
            self,
            self.exit_requested, data)


class ReadThread(TransportThread):
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue],
                 user_info: Any,
                 source: IO,
                 destination_queue: Queue,
                 length: int = 1024
                 ):

        super().__init__(identifier, signal_queues, user_info)
        self.source = source
        self.destination_queue = destination_queue
        self.length = length

    def read(self) -> Optional[bytes]:
        try:
            data = os.read(self.source.fileno(), self.length)
        except (ValueError, OSError):
            # The destination was most likely closed, nevertheless,
            # try to close it and indicate EOF.
            _try_close(self.source)
            return None
        return data or None

    def write(self,
              data: bytes
              ) -> bool:

        # We write to an unlimited queue, no need for timeout checking.
        self.destination_queue.put((self.user_info, IOState.ok, data))
        return True


class WriteThread(TransportThread):
    def __init__(self,
                 identifier: str,
                 signal_queues: list[Queue],
                 user_info: Any,
                 source_queue: Queue,
                 destination: IO
                 ):

        super().__init__(identifier, signal_queues, user_info)
        self.source_queue = source_queue
        self.destination = destination

    def read(self) -> Optional[bytes]:
        data = self.source_queue.get()
        if data is None:
            # Close stdin file descriptor here, since we know that no more
            # data will be sent to stdin.
            _try_close(self.destination)
        return data

    def write(self,
              data: bytes,
              ) -> bool:
        try:
            written = 0
            while written < len(data):
                written += os.write(
                    self.destination.fileno(),
                    data[written:])
                if self.exit_requested:
                    return written == len(data)
        except (BrokenPipeError, OSError, ValueError):
            # The destination was most likely closed, nevertheless,
            # try to close it and indicate EOF.
            _try_close(self.destination)
            return False
        return True
