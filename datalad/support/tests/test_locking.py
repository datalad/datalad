#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""
 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""
import os.path as op
from ..locking import lock_if_check_fails
from datalad.tests.utils import ok_exists, with_tempfile, ok_, eq_


@with_tempfile
def test_lock_if_check_fails(tempfile):
    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(True, None) as (check, lock):
        assert check is True
        assert lock is None
    assert check  # still available outside

    # and with a callable
    with lock_if_check_fails(lambda: "valuable", None) as (check, lock):
        eq_(check, "valuable")
        assert lock is None
    eq_(check, "valuable")

    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(False, tempfile) as (check, lock):
        ok_(lock.acquired)
        ok_exists(tempfile + '.lck')
    assert not op.exists(tempfile + '.lck')  # and it gets removed after

    # the same with providing operation
    # basic test, should never try to lock so filename is not important
    with lock_if_check_fails(False, tempfile, operation='get') as (check, lock):
        ok_(lock.acquired)
        ok_exists(tempfile + '.get-lck')
    assert not op.exists(tempfile + '.get-lck')  # and it gets removed after

    def subproc(q):
        with lock_if_check_fails(False, tempfile, blocking=False) as (_, lock2):
            q.put(lock2.acquired)

    from multiprocessing import Queue, Process
    q = Queue()
    p = Process(target=subproc, args=(q,))

    # now we need somehow to actually check the bloody lock functioning
    with lock_if_check_fails((op.exists, (tempfile,)), tempfile) as (check, lock):
        eq_(check, False)
        ok_(lock.acquired)
        # but now we will try to lock again, but we need to do it in another
        # process
        p.start()
        assert q.get() is False
        p.join()
        with open(tempfile, 'w') as f:
            pass
        ok_exists(tempfile)
    ok_exists(tempfile)

    # and we redo -- it will acquire it
    p = Process(target=subproc, args=(q,))
    p.start()
    ok_(q.get())
    p.join()
