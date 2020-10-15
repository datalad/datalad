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
    assert_repo_status,
    assert_raises,
    rmtree,
    skip_if,
    with_tempfile,
)

from datalad.support.exceptions import IncompleteResultsError


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

    pc = ProducerConsumer(producer(), consumer, jobs=jobs)
    assert_equal(list(pc), [0, 1, 2, "0", "1", "4"])


def test_ProducerConsumer():
        # Largely a smoke test, which only verifies correct results output
    for jobs in "auto", None, 1, 10:
        for PC in ProducerConsumer, ProducerConsumerProgressLog:
            yield check_ProducerConsumer, PC, jobs
        yield check_producing_consumer, jobs


@with_tempfile(mkdir=True)
def test_creatsubdatasets(topds_path, n=10):
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
    list(ProducerConsumer(paths, create_, safe_to_consume=no_parentds_in_futures, jobs=10))
    ds.save(paths)
    assert_repo_status(ds.repo)


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