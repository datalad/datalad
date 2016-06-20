# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for install-dataset command

"""

__docformat__ = 'restructuredtext'

from os.path import join as opj

from ...api import download_url
from ...tests.utils import eq_, assert_cwd_unchanged, assert_raises, \
    with_tempfile
from ...tests.utils import with_tree
from ...tests.utils import serve_path_via_http
from ...tests.utils import swallow_outputs


def test_download_url_exceptions():
    assert_raises(ValueError, download_url, ['url1', 'url2'], path=__file__)

    # is not in effect somehow :-/ TODO: investigate!
    with swallow_outputs() as cmo:
        # bogus urls can't be downloaded any ways
        with assert_raises(RuntimeError) as cm:
            download_url('http://example.com/bogus')
        eq_(str(cm.exception), "1 url(s) failed to download")


@assert_cwd_unchanged
@with_tree(tree=[
    ('file1.txt', 'abc'),
    ('file2.txt', 'abc'),
])
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_download_url_return(toppath, topurl, outdir):
    files = ['file1.txt', 'file2.txt']
    urls = [topurl + f for f in files]
    outfiles = [opj(outdir, f) for f in files]

    with swallow_outputs() as cmo:
        out1 = download_url(urls[0], path=outdir)
    eq_(out1, outfiles[:1])

    # can't overwrite
    with assert_raises(RuntimeError), \
        swallow_outputs() as cmo:
        out2 = download_url(urls, path=outdir)
        eq_(out2, outfiles[1:])  # only 2nd one

    with swallow_outputs() as cmo:
        out3 = download_url(urls, path=outdir, overwrite=True)
    eq_(out3, outfiles)
