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
import time
import uuid

from collections import defaultdict
from queue import Queue, Empty
from threading import Thread

from . import ansi_colors as colors
from ..log import log_progress
from ..utils import path_is_subpath


def _count_str(count, verb, omg=False):
    if count:
        msg = "{:d} {}".format(count, verb)
        if omg:
            msg = colors.color_word(msg, colors.RED)
        return msg


def no_parentds_in_futures(futures, path):
    """Return True if no path in futures keys is parentds for provided path

    Assumes that the future's key is the path.
    """
    # TODO: OPT.  Could benefit from smarter than linear time if not one at a time?
    #   or may be we should only go through active futures (still linear!)?
    return not any(path_is_subpath(path, p) for p in futures)


class ProducerConsumer:
    """
    """

    def __init__(self,
                 producer, consumer,
                 jobs=None,
                 safe_to_consume=None,
                 reraise_immediately=False,
                 agg=None,
                 # TODO: "absorb" into some more generic "logging" helper
                 # so could be used not only with consumers which yield our records
                 # 'agg' from above could also more relate to i
                 label="Total", unit="items",
                 lgr=None,
                 ):
        """

        Parameters
        ----------
        ...
        safe_to_consume: callable
          A callable which gets a dict of all known futures and current producer output.
          It should return True if we can proceed with current value from producer.
          If unsafe - we will wait.  WARNING: outside code should make sure about provider and
          safe_to_consume to play nicely or deadlock can happen.
        reraise_immediately: bool, optional
          If True, it would stop producer yielding values as soon as it detects that some
          exception has occurred (although there might still be values in the queue to be yielded
          which were collected before the exception was raised)
        """
        self.producer = producer
        self.consumer = consumer
        self.jobs = jobs
        self.safe_to_consume = safe_to_consume
        self.reraise_immediately = reraise_immediately
        self.agg = agg
        self.label = label
        self.unit = unit
        self.lgr = lgr

        self.total = None
        self.producer_finished = None
        self._executor = None
        self._exc = []

    def __del__(self):
        # if we are killed while executing, we should ask executor to shutdown
        executor = getattr(self, "_executor")
        if executor:
            executor.shutdown()

    def __iter__(self):
        self.producer_finished = False
        self._exc = []

        producer_queue = Queue()
        consumer_queue = Queue()

        def producer_worker():
            """That is the one which interrogates producer and updates .total"""
            total = None if self.agg else 0
            try:
                for value in self.producer:
                    producer_queue.put(value)
                    if self.agg:
                        total = (
                            self.agg(value, total) if total is not None else self.agg(value)
                        )
                    else:
                        total += 1
                    self.total = total
            except BaseException as e:
                self._exc.append(e)
            finally:
                self.producer_finished = True

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

        # LOGGING
        pid = str(uuid.uuid4())  # could be based on PID and time may be to be informative?
        lgr = self.lgr
        label = self.label
        if lgr is None:
            from .. import lgr
        log_progress(lgr.info, pid,
                     "%s: starting", self.label,
                     # will become known only later total=len(items),
                     label=self.label, unit=" " + self.unit)
        counts = defaultdict(int)

        futures = {}

        total_announced = self.total
        jobs = self.jobs or 1
        if jobs == "auto":
            # ATM there is no "auto" for this operation.  We will just make it ...
            # "auto" could be for some auto-scaling based on a single future time
            # to complete, scaling up/down.  TODO
            jobs = 5
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
                if (self.producer_finished and
                        not futures and
                        consumer_queue.empty() and
                        producer_queue.empty()):
                    break

                # LOGGING
                if self.total and total_announced != self.total:
                    # update total with new information
                    log_progress(
                        lgr.info,
                        pid,
                        None,  # I do not think there is something valuable to announce
                        total=self.total,
                        # unfortunately of no effect, so we cannot inform that more items to come
                        # unit=("+" if not it.finished else "") + " " + unit,
                        update=0  # not None, so it does not stop
                    )
                    total_announced = self.total

                # important!  We are using threads, so worker threads will be sharing CPU time
                # with this master thread. For it to become efficient, we should consume as much
                # as possible from producer asap and push it to executor.  So drain the queue
                while not producer_queue.empty():
                    done_useful = True
                    try:
                        job_args = producer_queue.get() # timeout=0.001)
                        if self.safe_to_consume:
                            # Sleep a little if we are not yet ready
                            # TODO: add some .debug level reporting based on elapsed time
                            # IIRC I did smth like growing exponentially delays somewhere (dandi?)
                            while not self.safe_to_consume(futures, job_args):
                                _prune_futures(futures, lgr) or sleeper()
                        # Current implementation, to provide depchecking, relies on unique
                        # args for the job
                        assert job_args not in futures
                        lgr.debug("Submitting worker future for %s", job_args)
                        futures[job_args] = executor.submit(consumer_worker, self.consumer, job_args)
                    except Empty:
                        pass

                # check active futures
                if not consumer_queue.empty():
                    done_useful = True

                    # ATM we do not bother of some "in order" reporting
                    # Just report as soon as any new record arrives
                    res = consumer_queue.get()
                    lgr.debug("Got %s from consumer_queue", res)
                    # LOGGING
                    counts[res["status"]] += 1
                    count_strs = (_count_str(*args)
                                  for args in [(counts["notneeded"], "skipped", False),
                                               (counts["error"], "failed", True)])
                    if counts["notneeded"] or counts["error"]:
                        label = "{} ({})".format(
                            self.label,
                            ", ".join(filter(None, count_strs)))

                    log_progress(
                        lgr.error if res["status"] == "error" else lgr.info,
                        pid,
                        "%s: processed result%s", self.label,
                        " for " + res["path"] if "path" in res else "",
                        label=label, update=1, increment=True)

                    yield res

                done_useful |= _prune_futures(futures, lgr)

                if not done_useful:  # you need some rest
                    # TODO: same here -- progressive logging
                    lgr.debug(
                        "Did nothing useful, sleeping. Have %s %s %s %s",
                        self.producer_finished,
                        futures,
                        consumer_queue.empty(),
                        producer_queue.empty())
                    sleeper()
                else:
                    sleeper.reset()

        self._executor = None

        # LOGGING
        log_progress(lgr.info, pid, "%s: done", self.label)
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
