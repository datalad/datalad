# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from datalad.support import path as op
from datalad.tests.utils_pytest import (
    assert_equal,
    known_failure_githubci_win,
    with_tempfile,
)
from datalad.utils import rmtree

from ..cookies import CookiesDB


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_no_blows(cookiesdir=None):
    cookies = CookiesDB(op.join(cookiesdir, 'mycookies'))
    # set the cookie
    cookies['best'] = 'mine'
    assert_equal(cookies['best'], 'mine')
    """
    Somehow this manages to trigger on conda but not on debian for me
    File "/home/yoh/anaconda-2018.12-3.7/envs/test-gitpython/lib/python3.7/shelve.py", line 125, in __setitem__
        self.dict[key.encode(self.keyencoding)] = f.getvalue()
    File "/home/yoh/anaconda-2018.12-3.7/envs/test-gitpython/lib/python3.7/dbm/dumb.py", line 216, in __setitem__
        self._index[key] = self._setval(pos, val)
    File "/home/yoh/anaconda-2018.12-3.7/envs/test-gitpython/lib/python3.7/dbm/dumb.py", line 178, in _setval
        with _io.open(self._datfile, 'rb+') as f:
        FileNotFoundError: [Errno 2] No such file or directory: '/home/yoh/.tmp/datalad_temp_test_no_blowsalnsw_wk/mycookies.dat'

    on Debian (python 3.7.3~rc1-1) I just get a warning: BDB3028 /home/yoh/.tmp/datalad_temp_test_no_blows58tdg67s/mycookies.db: unable to flush: No such file or directory
    """
    try:
        rmtree(cookiesdir)
    except OSError:
        # on NFS directory might still be open, so .nfs* lock file would prevent
        # removal, but it shouldn't matter and .close should succeed
        pass
    cookies.close()
