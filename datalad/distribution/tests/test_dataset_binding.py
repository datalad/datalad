# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test binding of functions to Dataset class

"""

from os.path import join as opj
from ..dataset import Dataset, datasetmethod
from datalad.tests.utils import assert_raises, eq_


def test_decorator():

    @datasetmethod
    def func(a, b, dataset=None, some_more=True):

        return {'a': a, 'b': b, 'dataset': dataset, 'some_more': some_more}

    ds = Dataset(opj('some', 'where'))

    orig = func(1, 2, ds, False)
    eq_(orig['a'], 1)
    eq_(orig['b'], 2)
    eq_(orig['dataset'], ds)
    eq_(orig['some_more'], False)

    # general call
    bound = ds.func(1, 2, False)
    eq_(orig, bound)

    # use default value
    bound = ds.func(1, 2)
    orig['some_more'] = True
    eq_(orig, bound)

    # too few arguments:
    assert_raises(TypeError, ds.func, 1)

    # too much arguments, by using original call with bound function,
    # raises proper TypeError:
    assert_raises(TypeError, ds.func, 1, 2, ds, False)

    # keyword argument 'dataset' is invalidated in Dataset-bound function:
    # raises proper TypeError:
    assert_raises(TypeError, ds.func, 1, 2, dataset='whatever')

    # test name parameter:
    @datasetmethod(name="new_name")
    def another(some, dataset=None):
        return some

    eq_(ds.new_name('whatever'), 'whatever')