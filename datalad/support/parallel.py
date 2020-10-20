# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for parallel execution

"""

__docformat__ = 'restructuredtext'

import concurrent.futures
import inspect
import sys
import time
import uuid

from collections import defaultdict
from queue import Queue, Empty
from threading import Thread

from . import ansi_colors as colors
from ..log import log_progress
from ..utils import path_is_subpath

import logging
lgr = logging.getLogger('datalad.parallel')


def _count_str(count, verb, omg=False):
    if count:
        msg = "{:d} {}".format(count, verb)
        if omg:
            msg = colors.color_word(msg, colors.RED)
        return msg


def no_parentds_in_futures(futures, path, skip=tuple()):
    """Return True if no path in futures keys is parentds for provided path

    Assumes that the future's key is the path.

    Parameters
    ----------
    skip: iterable
      Do not consider futures with paths in skip.  E.g. it could be top level
      dataset which we know it exists already, and it is ok to start with child
      process before it
    """
    # TODO: OPT.  Could benefit from smarter than linear time if not one at a time?
    #   or may be we should only go through active futures (still linear!)?
    return all(not path_is_subpath(path, p) or p in skip for p in futures)


def no_subds_in_futures(futures, path, skip=tuple()):
    """Return Tre if no path in futures keys is a subdataset for provided path

    See `no_parentds_in_futures` for more info
    """
    return all(not path_is_subpath(p, path) or p in skip for p in futures)


class ProducerConsumer:
    """Producer/Consumer implementation to (possibly) parallelize execution.

    It is "effective" only for Python >= 3.8.

    TODO
    `producer` must produce unique entries. AssertionError might be raised if
    the same entry is to be consumed.

    In parallel execution, results are yielded as soon as available, so order
    might not match the produced one.
    """

    # We cannot use threads with asyncio WitlessRunner inside until
    # 3.8.0 release (v3.8.0b2~37 to be exact)
    # See https://github.com/datalad/datalad/pull/5022#issuecomment-708716290
    _can_use_threads = sys.version_info >= (3, 8, 0, 'final')
    # Users should not specify -J100 and then just come complaining without
    # being informed that they are out of luck
    _alerted_already = False

    def __init__(self,
                 producer, consumer,
                 *,
                 jobs=None,
                 safe_to_consume=None,
                 producer_future_key=None,
                 reraise_immediately=False,
                 agg=None,
                 ):
        """

        Parameters
        ----------
        ...
        safe_to_consume: callable, optional
          A callable which gets a dict of all known futures and current producer output.
          It should return True if we can proceed with current value from producer.
          If unsafe - we will wait.  WARNING: outside code should make sure about provider and
          safe_to_consume to play nicely or deadlock can happen.
        producer_future_key: callable, optional
          A key function for a value from producer which will be used as a key in futures
          dictionary and output of which is passed to safe_to_consume
        reraise_immediately: bool, optional
          If True, it would stop producer yielding values as soon as it detects that some
          exception has occurred (although there might still be values in the queue to be yielded
          which were collected before the exception was raised)
        """
        self.producer = producer
        self.consumer = consumer
        self.jobs = jobs
        self.safe_to_consume = safe_to_consume
        self.producer_future_key = producer_future_key
        self.reraise_immediately = reraise_immediately
        self.agg = agg

        self.total = None if self.agg else 0
        self._jobs = None  # actual "parallel" jobs used
        # Relevant only for _iter_threads
        self._producer_finished = None
        self._producer_queue = None
        self._executor = None
        self._exc = []

    def __del__(self):
        # if we are killed while executing, we should ask executor to shutdown
        executor = getattr(self, "_executor")
        if executor:
            executor.shutdown()

    def _update_total(self, value):
        if self.agg:
            self.total = (
                self.agg(value, self.total) if self.total is not None else self.agg(value)
            )
        else:
            self.total += 1

    def __iter__(self):
        jobs = self.jobs
        if jobs in (None, "auto"):
            from datalad import cfg
            # ATM there is no "auto" for this operation, so in both auto and None
            # just consult max-jobs which can only be an int ATM.
            # "auto" could be for some auto-scaling based on a single future time
            # to complete, scaling up/down. Ten config variable could accept "auto" as well
            jobs = cfg.obtain('datalad.runtime.max-jobs')
        if jobs >= 1 and not self._can_use_threads:
            (lgr.debug if ProducerConsumer._alerted_already else lgr.warning)(
                "Got jobs=%d but we cannot use threads with Pythons versions prior 3.8.0. "
                "Will run serially", jobs)
            ProducerConsumer._alerted_already = True
            jobs = 0
        self._jobs = jobs
        if jobs == 0:
            yield from self._iter_serial()
        else:
            yield from self._iter_threads(jobs)

    def _iter_serial(self):
        # depchecker is not consulted, serial execution
        # reraise_immediately is also "always False by design"
        # To allow consumer to add to the queue
        self._producer_queue = producer_queue = Queue()

        def produce():
            # First consume all coming directly from producer and then go through all which
            # consumer might have added to the producer queue
            for args in self.producer:
                self._update_total(args)
                yield args
            # consumer could have added to the queue while we were still
            # producing
            while not producer_queue.empty():
                yield producer_queue.get()

        for args in produce():
            res = self.consumer(args)
            if inspect.isgenerator(res):
                lgr.debug("Got consumer worker which returned a generator %s", res)
                yield from res
            else:
                lgr.debug("Got straight result %s, not a generator", res)
                yield res

    def _iter_threads(self, jobs):
        self._producer_finished = False
        self._exc = []

        # To allow feeding producer queue with more entries, possibly from consumer!
        self._producer_queue = producer_queue = Queue()
        consumer_queue = Queue()

        def producer_worker():
            """That is the one which interrogates producer and updates .total"""
            try:
                for value in self.producer:
                    self.add_to_producer_queue(value)
            except BaseException as e:
                self._exc.append(e)
            finally:
                self._producer_finished = True

        def consumer_worker(callable, *args, **kwargs):
            """Since jobs could return a generator and we cannot really "inspect" for that
            """
            try:
                res = callable(*args, **kwargs)
                if inspect.isgenerator(res):
                    lgr.debug("Got consumer worker which returned a generator %s", res)
                    didgood = False
                    for r in res:
                        didgood = True
                        lgr.debug("Adding %s to queue", r)
                        consumer_queue.put(r)
                    if not didgood:
                        lgr.error("Nothing was obtained from %s :-(", res)
                else:
                    lgr.debug("Got straight result %s, not a generator", res)
                    consumer_queue.put(res)
            except BaseException as e:
                self._exc.append(e)

        producer_thread = Thread(target=producer_worker)
        producer_thread.start()

        futures = {}

        lgr.debug("Initiating ThreadPoolExecutor with %d jobs", jobs)
        # we will increase sleep_time when doing nothing useful
        sleeper = Sleeper()
        with concurrent.futures.ThreadPoolExecutor(jobs) as executor:
            self._executor = executor
            # yield from the producer_queue (.total and .finished could be accessed meanwhile)
            while True:
                done_useful = False
                if self.reraise_immediately and self._exc:
                    break
                if (self._producer_finished and
                        not futures and
                        consumer_queue.empty() and
                        producer_queue.empty()):
                    break

                # important!  We are using threads, so worker threads will be sharing CPU time
                # with this master thread. For it to become efficient, we should consume as much
                # as possible from producer asap and push it to executor.  So drain the queue
                while not producer_queue.empty():
                    done_useful = True
                    try:
                        job_args = producer_queue.get() # timeout=0.001)
                        job_key = self.producer_future_key(job_args) if self.producer_future_key else job_args
                        if self.safe_to_consume:
                            # Sleep a little if we are not yet ready
                            # TODO: add some .debug level reporting based on elapsed time
                            # IIRC I did smth like growing exponentially delays somewhere (dandi?)
                            while not self.safe_to_consume(futures, job_key):
                                _prune_futures(futures, lgr) or sleeper()
                        # Current implementation, to provide depchecking, relies on unique
                        # args for the job
                        assert job_key not in futures
                        lgr.debug("Submitting worker future for %s", job_args)
                        futures[job_key] = executor.submit(consumer_worker, self.consumer, job_args)
                    except Empty:
                        pass

                # check active futures
                if not consumer_queue.empty():
                    done_useful = True
                    # ATM we do not bother of some "in order" reporting
                    # Just report as soon as any new record arrives
                    res = consumer_queue.get()
                    lgr.debug("Got %s from consumer_queue", res)
                    yield res

                done_useful |= _prune_futures(futures, lgr)

                if not done_useful:  # you need some rest
                    # TODO: same here -- progressive logging
                    lgr.log(5,
                        "Did nothing useful, sleeping. Have "
                        "producer_finished=%s producer_queue.empty=%s futures=%s consumer_queue.empty=%s",
                            self._producer_finished,
                            producer_queue.empty(),
                            futures,
                            consumer_queue.empty(),
                            )
                    sleeper()
                else:
                    sleeper.reset()

        self._executor = None

        producer_thread.join()
        if self._exc:
            if len(self._exc) > 1:
                lgr.debug("%d exceptions were collected while performing execution in parallel. Only the first one "
                          "will be reraised", len(self._exc))
            raise self._exc[0]
        else:
            assert not futures, \
                "There is still %d active futures for following args: %s" \
                % (len(futures), ', '.join(futures))

    def add_to_producer_queue(self, value):
        self._producer_queue.put(value)
        self._update_total(value)


def _prune_futures(futures, lgr):
    """Removes .done from provided futures.

    Returns
    -------
    bool
      True if any future was removed
    """
    done_useful = False
    # remove futures which are done
    for args, future in list(futures.items()):
        if future.done():
            done_useful = True
            future_ = futures.pop(args)
            msg = ""
            if future_.exception():
                msg = " with an exception %s" % future_.exception()
            lgr.debug("Future for %r is done%s", args, msg)
    return done_useful


class Sleeper():
    def __init__(self):
        self.min_sleep_time = 0.001
        # but no more than to this max
        self.max_sleep_time = 0.1
        self.sleep_time = self.min_sleep_time

    def __call__(self):
        time.sleep(self.sleep_time)
        self.sleep_time = min(self.max_sleep_time, self.sleep_time * 2)

    def reset(self):
        self.sleep_time = self.min_sleep_time


class ProducerConsumerProgressLog(ProducerConsumer):
    """ProducerConsumer wrapper with log_progress reporting.

    It will update .total of the log_progress each time it changes (i.e. whenever
    producer produced new values to be consumed).
    """

    def __init__(self,
                 producer, consumer,
                 *,
                 log_filter=None,
                 label="Total", unit="items",
                 lgr=None,
                 **kwargs
                 ):
        """

        Parameters
        ----------
        producer, consumer, **kwargs
          Passed into ProducerConsumer. Most likely kwargs must not include 'agg' or
          if provided, it must return an 'int' value.
        log_filter: callable, optional
          If defined, only result records for which callable evaluates to True will be
          passed to log_progress
        label, unit: str, optional
          Provided to log_progress
        lgr: logger, optional
          Provided to log_progress. Local one is used if not provided
        """
        super().__init__(producer, consumer, **kwargs)
        self.log_filter = log_filter
        self.label = label
        self.unit = unit
        self.lgr = lgr

    def __iter__(self):
        pid = str(uuid.uuid4())  # could be based on PID and time may be to be informative?
        lgr_ = self.lgr
        label = self.label
        if lgr_ is None:
            lgr_ = lgr

        log_progress(lgr_.info, pid,
                     "%s: starting", self.label,
                     # will become known only later total=len(items),
                     label=self.label, unit=" " + self.unit)
        counts = defaultdict(int)
        total_announced = None  # self.total
        for res in super().__iter__():
            if self.total and total_announced != self.total:
                # update total with new information
                log_progress(
                    lgr_.info,
                    pid,
                    None,  # I do not think there is something valuable to announce
                    total=self.total,
                    # unfortunately of no effect, so we cannot inform that more items to come
                    # unit=("+" if not it.finished else "") + " " + unit,
                    update=0  # not None, so it does not stop
                )
                total_announced = self.total

            if not (self.log_filter and not self.log_filter(res)):
                counts[res["status"]] += 1
                count_strs = (_count_str(*args)
                              for args in [(counts["notneeded"], "skipped", False),
                                           (counts["error"], "failed", True)])
                if counts["notneeded"] or counts["error"]:
                    label = "{} ({})".format(
                        self.label,
                        ", ".join(filter(None, count_strs)))

                log_progress(
                    lgr_.error if res["status"] == "error" else lgr_.info,
                    pid,
                    "%s: processed result%s", self.label,
                    " for " + res["path"] if "path" in res else "",
                    label=label, update=1, increment=True)
            yield res
        log_progress(lgr_.info, pid, "%s: done", self.label)