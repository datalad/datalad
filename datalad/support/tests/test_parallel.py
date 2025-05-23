# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import sys
from functools import partial
from time import (
    sleep,
    time,
)

import pytest

# logging effects threading and causes some 'weak' tests to fail,
# so we will just skip those (well, if happens again -- disable altogether)
from datalad import lgr
from datalad.support import path as op
from datalad.support.exceptions import IncompleteResultsError
# absolute import only to be able to run test without `nose` so to see progress bar
from datalad.support.parallel import (
    ProducerConsumer,
    ProducerConsumerProgressLog,
    no_parentds_in_futures,
)
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_greater,
    assert_greater_equal,
    assert_raises,
    assert_repo_status,
    rmtree,
    slow,
    with_tempfile,
)

info_log_level = lgr.getEffectiveLevel() >= logging.INFO


@pytest.fixture(params=["auto", None, 1, 10])
def jobs(request):
    """Fixture to automagically sweep over a sample of "jobs" values
    """
    return request.param


@pytest.mark.parametrize("PC", [ProducerConsumer, ProducerConsumerProgressLog])
def test_ProducerConsumer_PC(PC, jobs):
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


def test_producing_consumer(jobs):
    def producer():
        yield from range(3)
    def consumer(i):
        yield i
        if isinstance(i, int):
            pc.add_to_producer_queue(str(i**2))

    # we auto-detect generator function producer
    pc = ProducerConsumer(producer, consumer, jobs=jobs)
    assert_equal(set(pc), {0, 1, 2, "0", "1", "4"})


def test_producer_future_key(jobs):
    if sys.version_info >= (3, 13) and jobs == 10:
        pytest.xfail("Known issue with Python 3.13 and jobs=10")

    def producer():
        for i in range(3):
            yield i, {"k": i**2}  # dict is mutable, will need a key

    def consumer(args):
        i, d = args
        yield i

    pc = ProducerConsumer(producer(), consumer, producer_future_key=lambda r: r[0], jobs=jobs)
    assert_equal(list(pc), [0, 1, 2])


@slow  # 12sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_creatsubdatasets(topds_path=None, n=2):
    from datalad.api import create
    from datalad.distribution.dataset import Dataset
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
    # we could get more, but for sure we should not get all 999 and not even a 100.
    # But some times we get some excursions above 100, so limiting to 300
    if info_log_level:
        assert_greater(300, len(results))
    assert_equal(results[:4], [0, 2, 3, 4])

    def producer():
        for i in range(10):
            sleep(0.0003)
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
    try:
        assert_greater_equal(len(results), 2)
    except AssertionError:
        # Possible TODO: if tests below would start failing too, move xfail to the level
        # of the entire test
        pytest.xfail(f"Rarely but happens. Got only {len(results)} instead of at least 2")

    # This test relies too much on threads scheduling to not hog up on handling
    # consumers, but if it happens so - they might actually consume all results
    # before producer decides to finally raise an exception.  As such it remains
    # flaky and thus not ran, but could be useful to test locally while
    # changing that logic.
    #
    # if info_log_level and not (on_windows or on_osx):
    #     # consumers should not be able to consume all produced items.
    #     # production of 10 should take 3 unites, while consumers 10/2 (jobs)
    #     # 5 units, so some should not have a chance.
    #     assert_greater_equal(8, len(results))

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
    # typically it should be [0, 1] but it does happen some times that
    # one other worker gets ahead and we get [0, 2]. As it is not per se the
    # purpose of this test to ensure absence of such race, we just allow for any
    # two from first 3 possible.
    assert len(set(inner()).intersection({0, 1, 2})) == 2
    consumed = sorted(consumed)
    assert_equal(consumed, list(range(len(consumed))))
    assert_greater_equal(len(consumed), 4)  # we should wait for that 2nd batch to finish
    if info_log_level:
        assert_greater_equal(20, len(consumed))


# `test_stalling` is a speculative test that is intended to detect stalled
# subprocess execution by assuming an upper limit for the execution time of the
# subprocess. Due to the nature of non-realtime process scheduling, this
# assumption is necessarily incorrect and might be validated in a perfectly
# working system. In other words, the test has the potential to create false
# positives.
# By raising the assumed maximum execution time, we try to reduce the number of
# false positives.
#
# The test exists because an earlier version of `WitlessRunner` was based on
# event loops and there was at least one stalling condition that manifested
# itself in python 3.7 (see:
# https://github.com/datalad/datalad/pull/5022#issuecomment-708716290). As of
# datalad version 0.16, event loops are no longer used in `WitlessRunner` and
# this test is a shot in the dark.
def test_stalling(kill=False):
    import concurrent.futures

    from datalad.runner.coreprotocols import StdOutErrCapture
    from datalad.runner.runner import WitlessRunner

    def worker():
        return WitlessRunner().run(["echo", "1"], StdOutErrCapture)

    t0 = time()
    result1 = worker()
    dt1 = time() - t0

    t0 = time()
    with concurrent.futures.ThreadPoolExecutor(1) as executor:
        future = executor.submit(worker)
        dt2_limit = max((5, dt1 * 100))
        while not future.done():
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
                raise AssertionError(f"Future has not finished in {dt2_limit}s")
        result2 = future.result()
    assert result1 == result2


@with_tempfile(mkdir=True)
def test_parallel_flyweights(topd=None):
    from datalad.support.gitrepo import GitRepo

    # ProducerConsumer relies on unique args to consumer so we will provide 2nd different arg
    def create_GitRepo(args):
        return GitRepo(args[0])

    # let's really hunt down race condition
    for batch in range(10):
        repopath = op.join(topd, str(batch))
        # should succeed and be the same thing
        # An example of errored run: https://github.com/datalad/datalad/issues/6598
        repos = list(
            ProducerConsumer(
                ((repopath, i) for i in range(10)),
                create_GitRepo,
                jobs=10
            )
        )
        assert op.exists(repopath)
        instances = set(map(id, repos))
        assert len(instances) == 1


if __name__ == '__main__':
    test_ProducerConsumer()
    # test_creatsubdatasets()
    # test_stalling(kill=True)
