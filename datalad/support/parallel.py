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

import datetime as dt
# import humanize
import inspect
import time
import uuid
from collections import defaultdict

from ..log import log_progress
from .iterators import IteratorWithAggregation

from . import ansi_colors as colors

from queue import Queue, Empty
from threading import Thread
import concurrent.futures


def _count_str(count, verb, omg=False):
    if count:
        msg = "{:d} {}".format(count, verb)
        if omg:
            msg = colors.color_word(msg, colors.RED)
        return msg


def producer_consumer(
        producer, consumer,
        label="Total", unit="items",
        lgr=None,
        # TODO: actually parallel
        # njobs=None,
        # order="as-complete",  # "original", anything else?
):
    """

    Parameters
    ----------
    """

    pid = str(uuid.uuid4())  # could be based on PID and time may be to be informative?
    base_label = label
    if lgr is None:
        from .. import lgr

    # TODO: code is based on @with_result_progress . for now we will just keep it centered
    # around processing "our" return records, but IMHO it should be made more flexible
    # so the same machinery could be used for any function
    counts = defaultdict(int)

    log_progress(lgr.info, pid,
                 "%s: starting", label,
                 #will become known only later total=len(items),
                 label=label, unit=" " + unit)
    # TODO: in principle is not needed if producer is not a generator, and we could just take __len__
    # but to simplify the logic we will just always use it for now
    class Count:
        def __init__(self):
            self.n = 0
        def __call__(self, item, _=None):
            self.n += 1
            return item

    count = Count()
    it = IteratorWithAggregation(producer, count)
    producer_finished = False
    for item in it:
        # keep updating total as producer gives more items
        if not producer_finished:
            log_progress(
                lgr.info,
                pid,
                None,  # I do not think there is something valuable to announce
                total=count.n,
                # unfortunately of no effect, so we cannot inform that more items to come
                # unit=("+" if not it.finished else "") + " " + unit,
                update=0  # not None, so it does not stop
            )
        if it.finished:
            producer_finished = True
        res = consumer(item)

        if inspect.isgenerator(res):
            ress = res
        else:
            ress = [res]

        for res in ress:
            counts[res["status"]] += 1
            count_strs = (_count_str(*args)
                          for args in [(counts["notneeded"], "skipped", False),
                                       (counts["error"], "failed", True)])
            if counts["notneeded"] or counts["error"]:
                label = "{} ({})".format(
                    base_label,
                    ", ".join(filter(None, count_strs)))

            log_progress(
                lgr.error if res["status"] == "error" else lgr.info,
                pid,
                "%s: processed result%s", base_label,
                " for " + res["path"] if "path" in res else "",
                label=label, update=1, increment=True)
            yield res
    log_progress(lgr.info, pid, "%s: done", base_label)
    # ??? how to make it leave the final record "automagically" or there is no such thing
    # so will log manually.  Actually it does duplicate the message already given
    # in non-interactive mode:
    #  [INFO   ]  Total 3 items done in 11 seconds at 0.254582 items/sec
    #  [INFO   ] Finished processing 3 items which started 11 seconds ago
    # so disabling for now -- I just think we should display that "Finished" in either case, how?
    # lgr.info("Finished processing %d %s which started %s", count.n, unit,
    #          # needs fresh humanize, 2.3.0-1 did not have it
    #          # humanize.precisedelta(dt.datetime.now() - t0),
    #          humanize.naturaltime(dt.datetime.now() - t0)
    #          )


class ProducerConsumer:
    """
    """

    def __init__(self,
                 producer, consumer,
                 njobs=None,
                 consumer_depchecker=None,
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
        reraise_immediately: bool, optional
          If True, it would stop producer yielding values as soon as it detects that some
          exception has occurred (although there might still be values in the queue to be yielded
          which were collected before the exception was raised)
        """
        self.producer = producer
        self.consumer = consumer
        self.njobs = njobs
        self.consumer_depchecker = consumer_depchecker
        self.reraise_immediately = reraise_immediately
        self.agg = agg
        self.label = label
        self.unit = unit
        self.lgr = lgr

        self.total = None
        self.producer_finished = None
        self._exc = None

    def __iter__(self):
        self.producer_finished = False
        self._exc = None

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
                self._exc = e
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
                # TODO: avoid masking exceptions, collect all???
                self._exc = e

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
        total_announced = False
        njobs = self.njobs or 1
        lgr.debug("Initiating ThreadPoolExecutor with %d jobs", njobs)
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(njobs) as executor:
            # yield from the producer_queue (.total and .finished could be accessed meanwhile)
            while True:
                done_useful = False
                if self.reraise_immediately and self._exc is not None:
                    # stop all possibly running futures
                    # executor.shutdown()
                    break
                if (self.producer_finished and
                        not futures and
                        consumer_queue.empty() and
                        producer_queue.empty()):
                    break

                # LOGGING
                if not total_announced and self.producer_finished:
                    log_progress(
                        lgr.info,
                        pid,
                        None,  # I do not think there is something valuable to announce
                        total=self.total,
                        # unfortunately of no effect, so we cannot inform that more items to come
                        # unit=("+" if not it.finished else "") + " " + unit,
                        update=0  # not None, so it does not stop
                    )
                    total_announced = True

                # important!  We are using threads, so worker threads will be sharing CPU time
                # with this master thread. For it to become efficient, we should consume as much
                # as possible from producer asap and push it to executor.  So drain the queue
                while not producer_queue.empty():
                    done_useful = True
                    try:
                        job_args = producer_queue.get() # timeout=0.001)
                        if self.consumer_depchecker:
                            # Sleep a little if we are not yet ready
                            # TODO: add some .debug level reporting based on elapsed time
                            # IIRC I did smth like growing exponentially delays somewhere (dandi?)
                            while not self.consumer_depchecker(futures, job_args):
                                time.sleep(0.01)
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

                # remove futures which are done
                for args, future in list(futures.items()):
                    if future.done():
                        done_useful = True
                        future_ = futures.pop(args)
                        msg = ""
                        if future_.exception():
                            msg = " with an exception %s" % future_.exception()
                        lgr.debug("Future for %r is done%s", args, msg)

                if not done_useful:  # you need some rest
                    # TODO: same here -- progressive logging
                    lgr.debug(
                        "Did nothing useful, sleeping. Have %s %s %s %s",
                        self.producer_finished,
                        futures,
                        consumer_queue.empty(),
                        producer_queue.empty())
                    time.sleep(0.2)

        # LOGGING
        log_progress(lgr.info, pid, "%s: done", self.label)
        assert not futures
        producer_thread.join()
        if self._exc is not None:
            raise self._exc
