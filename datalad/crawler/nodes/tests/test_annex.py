# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj, exists
from datalad.tests.utils import with_tempfile, eq_, ok_, SkipTest

from ..annex import initiate_handle

@with_tempfile(mkdir=True)
def test_initialize_handle(path):
    handle_path = opj(path, 'test')
    datas = list(initiate_handle('testtemplate', 'testhandle', path=handle_path)())
    assert(len(datas), 1); data = datas[0]
    eq_(data['handle_path'], handle_path)
    ok_(exists, opj(handle_path, '.datalad', 'crawl.cfg'))
    raise SkipTest("TODO much more")
