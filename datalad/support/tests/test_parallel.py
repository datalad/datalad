# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from time import sleep, time

# absolute import only to be able to run test without `nose` so to see progress bar
from datalad.support.parallel import producer_consumer
from datalad.tests.utils import with_tempfile

def test_producer_consumer():
    def slowprod(n, secs=0.1):
        for i in range(n):
            yield i
            sleep(secs)

    def slowcons(i):
        # so takes longer to consume than to produce and progress bar will appear
        # after slowprod is done producing
        #print(f"Consuming {i}")
        #t0 = time()
        sleep(0.2)
        #print(f"Consumed {i} in {time() - t0}")
        yield {
            "status": "ok" if i % 2 else "error"
        }
    list(producer_consumer(
        slowprod(10),
        slowcons,
    ))


@with_tempfile(mkdir=True)
def test_creatsubdatasets(topds_path, n=10):
    from datalad import lgr
    from datalad.distribution.dataset import Dataset
    ds = Dataset(topds_path).create(cfg_proc="yoda")
    list(producer_consumer(
        ("subds%d" % i for i in range(n)),
        lambda n: ds.create(n, cfg_proc="yoda", result_xfm=None, return_type='generator')
    ))


if __name__ == '__main__':
    test_producer_consumer()
    # test_creatsubdatasets()