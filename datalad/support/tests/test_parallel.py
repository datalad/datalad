# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from time import sleep, time
from functools import partial

from datalad.support import path as op

# absolute import only to be able to run test without `nose` so to see progress bar
from datalad.support.parallel import (
    ProducerConsumer,
    ProducerConsumerProgressLog,
    no_parentds_in_futures,
)
from datalad.tests.utils import (
    assert_equal,
    assert_greater,
    assert_greater_equal,
    assert_repo_status,
    assert_raises,
    known_failure_osx,
    rmtree,
    on_windows,
    on_osx,
    skip_if,
    slow,
    with_tempfile,
)

from datalad.support.exceptions import IncompleteResultsError

# logging effects threading and causes some 'weak' tests to fail,
# so we will just skip those (well, if happens again -- disable altogether)
from datalad import lgr
import logging

info_log_level = lgr.getEffectiveLevel() >= logging.INFO


def check_ProducerConsumer(PC, jobs):
    def slowprod(n, secs=0.001):
        for i in range(n):
            yield i
            sleep(secs)

    def slowcons(i):
        # so takes longer to consume than to produce and progress bar will appear
        # after slowprod is done producing
        sleep(0.002)
        yield from fastcons(i)

    def fastcons(i):
        # we should still work correctly if consumer is fast!
        yield {
            "i": i, "status": "ok" if i % 2 else "error"
        }

    for cons in fastcons, slowcons:
        # sorted since order of completion is not guaranteed
        assert_equal(
            sorted(PC(
                slowprod(10),
                cons,
                jobs=jobs),
                key=lambda r: r['i']),
            [{"i": i, "status": "ok" if i % 2 else "error"} for i in range(10)])


def check_producing_consumer(jobs):
    def producer():
        yield from range(3)
    def consumer(i):
        yield i
        if isinstance(i, int):
            pc.add_to_producer_queue(str(i**2))

    # we auto-detect generator function producer
    pc = ProducerConsumer(producer, consumer, jobs=jobs)
    assert_equal(list(pc), [0, 1, 2, "0", "1", "4"])


def check_producer_future_key(jobs):
    def producer():
        for i in range(3):
            yield i, {"k": i**2}  # dict is mutable, will need a key

    def consumer(args):
        i, d = args
        yield i

    pc = ProducerConsumer(producer(), consumer, producer_future_key=lambda r: r[0], jobs=jobs)
    assert_equal(list(pc), [0, 1, 2])


def test_ProducerConsumer():
        # Largely a smoke test, which only verifies correct results output
    for jobs in "auto", None, 1, 10:
        for PC in ProducerConsumer, ProducerConsumerProgressLog:
            yield check_ProducerConsumer, PC, jobs
        yield check_producing_consumer, jobs
        yield check_producer_future_key, jobs


@slow  # 12sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_creatsubdatasets(topds_path, n=2):
    from datalad.distribution.dataset import Dataset
    from datalad.api import create
    ds = Dataset(topds_path).create()
    paths = [op.join(topds_path, "subds%d" % i) for i in range(n)]
    paths.extend(op.join(topds_path, "subds%d" % i, "subsub%d" %k) for i in range(n) for k in range(2))
    # To allow for parallel execution without hitting the problem of
    # a lock in the super dataset, we create all subdatasets, and then
    # save them all within their superdataset
    create_ = partial(create,  # cfg_proc="yoda",
                      result_xfm=None, return_type='generator')
    # if we flip the paths so to go from the end, create without --force should fail
    # and we should get the exception (the first one encountered!)
    # Note: reraise_immediately is of "concern" only for producer. since we typically
    # rely on outside code to do the killing!
    assert_raises(IncompleteResultsError, list, ProducerConsumer(paths[::-1], create_, jobs=5))
    # we are in a dirty state, let's just remove all those for a clean run
    rmtree(topds_path)

    # and this one followed by save should be good IFF we provide our dependency checker
    ds = Dataset(topds_path).create()
    list(ProducerConsumer(paths, create_, safe_to_consume=no_parentds_in_futures, jobs=5))
    ds.save(paths)
    assert_repo_status(ds.repo)


@known_failure_osx  # https://github.com/datalad/datalad/issues/5309
@skip_if(not ProducerConsumer._can_use_threads, msg="Test relies on having parallel execution")
def test_gracefull_death():

    def assert_provides_and_raises(pc, exception, target=None):
        """Helper to get all results before exception is raised"""
        results = []
        with assert_raises(exception):
            for r in pc:
                results.append(r)
        # results should be sorted since we do not guarantee order
        results = sorted(results)
        if target is not None:
            assert_equal(results, target)
        return results

    def interrupted_producer():
        yield 1
        raise ValueError()

    def consumer(i):
        sleep(0.001)
        yield i

    assert_provides_and_raises(
        ProducerConsumer(interrupted_producer(), consumer, jobs=3), ValueError, [1])

    def faulty_consumer(i):
        sleep(0.001)
        if i == 1:
            raise ValueError()
        return i

    # so we do not get failed, but other parallel ones finish their job
    results = assert_provides_and_raises(
        ProducerConsumer(range(1000), faulty_consumer, jobs=5), ValueError)
    # and analysis of futures to raise an exception can take some time etc, so
    # we could get more, but for sure we should not get all 999 and not even a 100
    if info_log_level:
        assert_greater(100, len(results))
    assert_equal(results[:4], [0, 2, 3, 4])

    def producer():
        for i in range(10):
            sleep(0.0001)
            yield i
        raise ValueError()
    # by default we do not stop upon producer failing
    assert_provides_and_raises(
        ProducerConsumer(producer(), consumer, jobs=2), ValueError, list(range(10)))
    # if producer produces more than we can as quickly consume but then fails
    # ATM we do not proceed to consume other items, but fail when we finish
    # consuming until the time point when producer has failed
    # by default we do not stop upon producer failing
    results = assert_provides_and_raises(
        ProducerConsumer(producer(), consumer, reraise_immediately=True, jobs=2),
        ValueError)
    # we will get some results, seems around 4 and they should be "sequential"
    assert_equal(results, list(range(len(results))))
    assert_greater_equal(len(results), 2)
    if info_log_level and not (on_windows or on_osx):
        # windows does not behave according to the initial performance
        # expectations gh-5296 (~9), and neither does a macosx cloud instance
        # (~7)
        assert_greater_equal(6, len(results))

    # Simulate situation close to what we have when outside code consumes
    # some yielded results and then "looses interest" (on_failure="error").
    # In this case we should still exit gracefully (no GeneratorExit warnings),
    # not over-produce, and also do not kill already running consumers
    consumed = []
    def inner():
        def consumer(i):
            sleep(0.01)
            consumed.append(i)
            return i
        pc = iter(ProducerConsumer(range(1000), consumer, jobs=2))
        yield next(pc)
        yield next(pc)
    assert_equal(sorted(inner()), [0, 1])
    consumed = sorted(consumed)
    assert_equal(consumed, list(range(len(consumed))))
    assert_greater_equal(len(consumed), 4)  # we should wait for that 2nd batch to finish
    if info_log_level:
        assert_greater_equal(20, len(consumed))


# it will stall! https://github.com/datalad/datalad/pull/5022#issuecomment-708716290
@skip_if(not ProducerConsumer._can_use_threads, msg="Known to be buggy/stall")
def test_stalling(kill=False):
    import concurrent.futures
    from datalad.cmd import WitlessRunner

    def worker():
        WitlessRunner().run(["echo", "1"])

    t0 = time()
    v1 = worker()
    dt1 = time() - t0

    t0 = time()
    with concurrent.futures.ThreadPoolExecutor(1) as executor:
        # print("submitting")
        future = executor.submit(worker)
        dt2_limit = dt1 * 5
        # print("waiting for up to %.2f sec" % dt2_limit)
        while not future.done():
            # print("not yet")
            sleep(dt1/3)
            if time() - t0 > dt2_limit:
                # does not even shutdown
                # executor.shutdown(wait=False)
                if kill:
                    # raising an exception isn't enough!
                    print("exceeded")
                    import os
                    import signal
                    os.kill(os.getpid(), signal.SIGTERM)
                raise AssertionError("Future has not finished in 5x time")
        v2 = future.result()
    assert_equal(v1, v2)


if __name__ == '__main__':
    test_ProducerConsumer()
    # test_creatsubdatasets()
    # test_stalling(kill=True)
