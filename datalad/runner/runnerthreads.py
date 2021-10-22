import logging
import os
import threading
import time
from abc import (
    abstractmethod,
    ABCMeta,
)
from queue import Queue
from typing import (
    IO,
    List,
    Union,
)


lgr = logging.getLogger("datalad.runner.runnerthreads")


class DataCopyThread(threading.Thread, metaclass=ABCMeta):

    def __init__(self,
                 source: Union[IO, Queue],
                 destination: Union[IO, Queue],
                 ):

        super().__init__(daemon=True)

        self.source = source
        self.destination = destination
        self.exit_requested = False

    def request_exit(self):
        """
        Request the thread to exit. This is not guaranteed to
        have any effect, because the thread might be waiting in
        self.get_data() or on self.write_data().
        """
        self.exit_requested = True

    @abstractmethod
    def read_data(self) -> Union[str, bytes, None]:
        raise NotImplementedError

    @abstractmethod
    def write_data(self, data: Union[str, bytes]):
        raise NotImplementedError

    def signal_termination(self):
        pass

    def run(self):
        lgr.log(5, "%s started", self)

        data = None
        while not self.exit_requested:
            data = self.read_data()
            if data in (b"", None) or self.exit_requested:
                break
            self.write_data(data)

        self.signal_termination()
        lgr.log(5, "%s exiting (last data was: %s)", self, data)


class ReaderThread(DataCopyThread):

    def __init__(self,
                 file: IO,
                 q: Queue,
                 command: Union[str, List]):
        """
        Parameters
        ----------
        file:
          File object from which the thread will read data
          and write it into the queue. This is usually the
          read end of a pipe.
        q:
          A queue into which the thread writes what it reads
          from file.
        command:
          The command for which the thread was created. This
          is mainly used to improve debug output messages.
        """
        super().__init__(source=file, destination=q)
        self._file = file
        self._queue = q
        self.command = command

    def __str__(self):
        return f"{type(self).__name__}({self._file}, " \
               f"{self._queue}, {self.command})"

    def read_data(self) -> Union[str, bytes, None]:
        return os.read(self.source.fileno(), 1024)

    def write_data(self, data: Union[str, bytes]):
        self.destination.put((self.source.fileno(), data, time.time()))

    def signal_termination(self):
        self.destination.put((self.source.fileno(), None, time.time()))


class WriterThread(DataCopyThread):
    def __init__(self,
                 input_queue: Queue,
                 file: IO,
                 signal_queue: Queue,
                 command: Union[str, List] = ""):
        """
        Parameters
        ----------
        input_queue:
          A queue from which data is read and written to the process,
          a None-data object indicates that all stdin_data was written
          and will lead to this thread exiting.
        file:
          file-like representing stdin of the subprocess
        signal_queue:
          A queue to signal the main thread, when we are exiting.
        command:
          The command for which the thread was created. This
          is mainly used to improve debug output messages.
        """
        super().__init__(source=input_queue, destination=file)
        self._input_queue = input_queue
        self._file = file
        self.signal_queue = signal_queue
        self.command = command

    def __str__(self):
        return (
            f"{type(self).__name__}({self._input_queue}, {self._file}, "
            f"{self.signal_queue}, {self.command})")

    def read_data(self) -> Union[str, bytes, None]:
        return self.source.get()

    def write_data(self, data: Union[str, bytes]):
        try:
            os.write(self.destination.fileno(), data.encode())
        except BrokenPipeError:
            lgr.debug(f"{self} broken pipe")
            self.request_exit()

    def signal_termination(self):
        self.signal_queue.put((self._file.fileno(), None, time.time()))


