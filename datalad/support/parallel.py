# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import logging
import sys
import time
import uuid
from collections import defaultdict
from queue import (
    Empty,
    Queue,
)
from threading import Thread

from datalad.support.exceptions import CapturedException

from ..log import log_progress
from ..utils import path_is_subpath
from . import ansi_colors as colors

lgr = logging.getLogger('datalad.parallel')


def _count_str(count, verb, omg=False):
    if count:
        msg = "{:d} {}".format(count, verb)
        if omg:
            msg = colors.color_word(msg, colors.RED)
        return msg


#
# safe_to_consume  helpers
#

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
    """Return True if no path in futures keys is a subdataset for provided path

    See `no_parentds_in_futures` for more info
    """
    return all(not path_is_subpath(p, path) or p in skip for p in futures)


class ProducerConsumer:
    """Producer/Consumer implementation to (possibly) parallelize execution.

    It is an iterable providing a multi-threaded producer/consumer implementation,
    where there could be multiple consumers for items produced by a producer.  Since
    in DataLad majority of time is done in IO interactions with outside git and git-annex
    processes, and since we typically operate across multiple datasets, multi-threading
    across datasets operations already provides a significant performance benefit.

    All results from consumers are all yielded as soon as they are produced by consumers.
    Because this implementation is based on threads, `producer` and `consumer` could
    be some "closures" within code, thus having lean interface and accessing
    data from shared "outer scope".

    Notes
    -----
    - with jobs > 1, results are yielded as soon as available, so order
      might not match the one provided by "producer".
    - `producer` must produce unique entries. AssertionError might be raised if
      the same entry is to be consumed.
    - `consumer` can add to the queue of items produced by producer via
      `.add_to_producer_queue`. This allows for continuous reuse of the same
      instance in recursive operations (see `get` use of ProducerConsumer).
    - if producer or consumer raise an exception, we will try to "fail gracefully",
      unless subsequent Ctrl-C is pressed, we will let already running jobs to
      finish first.

    Examples
    --------
    A simple and somewhat boring example to count lines in '*.py'

    >>> from glob import glob
    >>> from pprint import pprint
    >>> from datalad.support.parallel import ProducerConsumer
    >>> def count_lines(fname):
    ...     with open(fname) as f:
    ...         return fname, len(f.readlines())
    >>> pprint(dict(ProducerConsumer(glob("*.py"), count_lines)))  # doctest: +SKIP
    {'setup.py': 182, 'versioneer.py': 2136}

    More usage examples could be found in `test_parallel.py` and around the
    codebase `addurls.py`, `get.py`, `save.py`, etc.
    """

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
        producer: iterable
          Provides items to feed a consumer with
        consumer: callable
          Is provided with items produced by producer.  Multiple consumers might
          operate in parallel threads if jobs > 1
        jobs: int, optional
          If None or "auto", 'datalad.runtime.max-jobs' configuration variable is
          consulted.  With jobs=0 there is no threaded execution whatsoever.  With
          jobs=1 there is a separate thread for the producer, so in effect with jobs=1
          some parallelization between producer (if it is a generator) and consumer
          could be achieved, while there is only a single thread available for consumers.
        safe_to_consume: callable, optional
          A callable which gets a dict of all known futures and current item from producer.
          It should return `True` if executor can proceed with current value from producer.
          If not (unsafe to consume) - we will wait.
          WARNING: outside code should make sure about provider and `safe_to_consume` to
          play nicely or a very suboptimal behavior or possibly even a deadlock can happen.
        producer_future_key: callable, optional
          A key function for a value from producer which will be used as a key in futures
          dictionary and output of which is passed to safe_to_consume.
        reraise_immediately: bool, optional
          If True, it would stop producer yielding values as soon as it detects that some
          exception has occurred (although there might still be values in the queue to be yielded
          which were collected before the exception was raised).
        agg: callable, optional
          Should be a callable with two arguments: (item, prior total) and return a new total
          which will get assigned to .total of this object.  If not specified, .total is
          just a number of items produced by the producer.
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
        self._producer_exception = None
        self._producer_interrupt = None
        # so we could interrupt more or less gracefully
        self._producer_thread = None
        self._executor = None
        self._futures = {}
        self._interrupted = False

    @property
    def interrupted(self):
        return self._interrupted

    def __del__(self):
        # if we are killed while executing, we should ask executor to shutdown
        shutdown = getattr(self, "shutdown", None)
        if shutdown:
            shutdown(force=True)

    def shutdown(self, force=False, exception=None):
        if self._producer_thread and self._producer_thread.is_alive():
            # we will try to let the worker to finish "gracefully"
            self._producer_interrupt = f"shutdown due to {exception}"

        # purge producer queue
        if self._producer_queue:
            while not self._producer_queue.empty():
                self._producer_queue.get()

        lgr.debug("Shutting down %s with %d futures. Reason: %s",
                  self._executor, len(self._futures), exception)

        if not force:
            # pop not yet running or done futures.
            # Those would still have a chance to yield results and finish gracefully
            # or their exceptions to be bubbled up FWIW.
            ntotal = len(self._futures)
            ncanceled = 0
            nrunning = 0
            # Do in reverse order so if any job still manages
            # to sneak in, it would be the earlier submitted one.
            for k, future in list(self._futures.items())[::-1]:
                running = future.running()
                nrunning += int(running)
                if not (running or future.done()):
                    if self._futures.pop(k).cancel():
                        ncanceled += 1
            lgr.info("Canceled %d out of %d jobs. %d left running.",
                     ncanceled, ntotal, nrunning)
        else:
            # just pop all entirely
            for k in list(self._futures)[::-1]:
                self._futures.pop(k).cancel()
            if self._executor:
                self._executor.shutdown()
                self._executor = None
            if exception:
                raise exception
        lgr.debug("Finished shutdown with force=%s due to exception=%r", force, exception)

    def _update_total(self, value):
        if self.agg:
            self.total = (
                self.agg(value, self.total) if self.total is not None else self.agg(value)
            )
        else:
            self.total += 1

    @classmethod
    def get_effective_jobs(cls, jobs):
        """Return actual number of jobs to be used.

        It will account for configuration variable ('datalad.runtime.max-jobs') and possible
        other requirements (such as version of Python).
        """
        if jobs in (None, "auto"):
            from datalad import cfg

            # ATM there is no "auto" for this operation, so in both auto and None
            # just consult max-jobs which can only be an int ATM.
            # "auto" could be for some auto-scaling based on a single future time
            # to complete, scaling up/down. Ten config variable could accept "auto" as well
            jobs = cfg.obtain('datalad.runtime.max-jobs')
        return jobs

    def __iter__(self):
        self._jobs = self.get_effective_jobs(self.jobs)
        if self._jobs == 0:
            yield from self._iter_serial()
        else:
            yield from self._iter_threads(self._jobs)

    def _iter_serial(self):
        # depchecker is not consulted, serial execution
        # reraise_immediately is also "always False by design"
        # To allow consumer to add to the queue
        self._producer_queue = producer_queue = Queue()

        def produce():
            # First consume all coming directly from producer and then go through all which
            # consumer might have added to the producer queue
            for args in self._producer_iter:
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

    @property
    def _producer_iter(self):
        """A little helper to also support generator functions"""
        return self.producer() if inspect.isgeneratorfunction(self.producer) else self.producer

    def _iter_threads(self, jobs):
        self._interrupted = False
        self._producer_finished = False
        self._producer_exception = None
        self._producer_interrupt = None

        # To allow feeding producer queue with more entries, possibly from consumer!
        self._producer_queue = producer_queue = Queue()
        consumer_queue = Queue()

        def producer_worker():
            """That is the one which interrogates producer and updates .total"""
            try:
                for value in self._producer_iter:
                    if self._producer_interrupt:
                        raise InterruptedError("Producer thread was interrupted due to %s" % self._producer_interrupt)
                    self.add_to_producer_queue(value)
            except InterruptedError:
                pass  # There is some outside exception which will be raised
            except BaseException as e:
                self._producer_exception = e
            finally:
                self._producer_finished = True

        def consumer_worker(callable, *args, **kwargs):
            """Since jobs could return a generator and we cannot really "inspect" for that
            """
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

        self._producer_thread = Thread(target=producer_worker)
        self._producer_thread.start()
        self._futures = futures = {}

        lgr.debug("Initiating ThreadPoolExecutor with %d jobs", jobs)
        # we will increase sleep_time when doing nothing useful
        sleeper = Sleeper()
        interrupted_by_exception = None
        with concurrent.futures.ThreadPoolExecutor(jobs) as executor:
            self._executor = executor
            # yield from the producer_queue (.total and .finished could be accessed meanwhile)
            while True:
                try:
                    done_useful = False
                    if self.reraise_immediately and self._producer_exception and not interrupted_by_exception:
                        # so we have a chance to exit gracefully
                        # No point to reraise if there is already an exception which was raised
                        # which might have even been this one
                        lgr.debug("Reraising an exception from producer as soon as we found it")
                        raise self._producer_exception
                    if (self._producer_finished and
                            not futures and
                            consumer_queue.empty() and
                            producer_queue.empty()):
                        # This will let us not "escape" the while loop and reraise any possible exception
                        # within the loop if we have any.
                        # Otherwise we might see "RuntimeError: generator ignored GeneratorExit"
                        # when e.g. we did continue upon interrupted_by_exception, and then
                        # no other subsequent exception was raised and we left the loop
                        raise _FinalShutdown()

                    # important!  We are using threads, so worker threads will be sharing CPU time
                    # with this master thread. For it to become efficient, we should consume as much
                    # as possible from producer asap and push it to executor.  So drain the queue
                    while not (producer_queue.empty() or interrupted_by_exception):
                        done_useful = True
                        try:
                            job_args = producer_queue.get() # timeout=0.001)
                            job_key = self.producer_future_key(job_args) if self.producer_future_key else job_args
                            if self.safe_to_consume:
                                # Sleep a little if we are not yet ready
                                # TODO: add some .debug level reporting based on elapsed time
                                # IIRC I did smth like growing exponentially delays somewhere (dandi?)
                                while not self.safe_to_consume(futures, job_key):
                                    self._pop_done_futures(lgr) or sleeper()
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

                    done_useful |= self._pop_done_futures(lgr)

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
                except (_FinalShutdown, GeneratorExit):
                    self.shutdown(force=True, exception=self._producer_exception or interrupted_by_exception)
                    break  # if there were no exception to raise
                except BaseException as exc:
                    ce = CapturedException(exc)
                    self._interrupted = True
                    if interrupted_by_exception:
                        # so we are here again but now it depends why we are here
                        if isinstance(exc, KeyboardInterrupt):
                            lgr.warning("Interrupted via Ctrl-C.  Forcing the exit")
                            self.shutdown(force=True, exception=exc)
                        else:
                            lgr.warning(
                                "One more exception was received while "
                                "trying to finish gracefully: %s",
                                ce)
                            # and we go back into the loop until we finish or there is Ctrl-C
                    else:
                        interrupted_by_exception = exc
                        lgr.warning(
                            "Received an exception %s. Canceling not-yet "
                            "running jobs and waiting for completion of "
                            "running. You can force earlier forceful exit "
                            "by Ctrl-C.", ce)
                        self.shutdown(force=False, exception=exc)

    def add_to_producer_queue(self, value):
        self._producer_queue.put(value)
        self._update_total(value)

    def _pop_done_futures(self, lgr):
        """Removes .done from provided futures.

        Returns
        -------
        bool
          True if any future was removed
        """
        done_useful = False
        # remove futures which are done
        for args, future in list(self._futures.items()):
            if future.done():
                done_useful = True
                future_ = self._futures.pop(args)
                exception = future_.exception()
                if exception:
                    lgr.debug("Future for %r raised %s.  Re-raising to trigger graceful shutdown etc", args, exception)
                    raise exception
                lgr.debug("Future for %r is done", args)
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

    It is to be used around a `consumer` which returns or yields result records.
    If that is not the case -- use regular `ProducerConsumer`.

    It will update `.total` of the `log_progress` each time it changes (i.e. whenever
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
                     label=self.label, unit=" " + self.unit,
                     noninteractive_level=5)
        counts = defaultdict(int)
        total_announced = None  # self.total
        for res in super().__iter__():
            if self.total and total_announced != self.total:
                # update total with new information
                log_progress(
                    lgr_.info,
                    pid,
                    "",  # None flips python 3.6.7 in conda if nose ran without -s
                         # I do not think there is something
                    # valuable to announce
                    total=self.total,
                    # unfortunately of no effect, so we cannot inform that more items to come
                    # unit=("+" if not it.finished else "") + " " + unit,
                    update=0,  # not None, so it does not stop
                    noninteractive_level=5
                )
                total_announced = self.total

            if not (self.log_filter and not self.log_filter(res)):
                counts[res["status"]] += 1
                count_strs = [_count_str(*args)
                              for args in [(counts["notneeded"], "skipped", False),
                                           (counts["error"], "failed", True)]]
                if counts["notneeded"] or counts["error"] or self.interrupted:
                    strs = count_strs
                    if self.interrupted:
                        strs.append("exiting!")
                    label = "{} ({})".format(
                        self.label,
                        ", ".join(filter(None, count_strs)))

                log_progress(
                    lgr_.error if res["status"] == "error" else lgr_.info,
                    pid,
                    "%s: processed result%s", self.label,
                    " for " + res["path"] if "path" in res else "",
                    label=label, update=1, increment=True,
                    noninteractive_level=5)
            yield res
        log_progress(lgr_.info, pid, "%s: done", self.label,
                     noninteractive_level=5)


class _FinalShutdown(Exception):
    """Used internally for the final forceful shutdown if any exception did happen"""
    pass
