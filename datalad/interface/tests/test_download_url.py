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
from ...tests.utils import eq_, assert_cwd_unchanged, assert_in, \
    assert_message, assert_raises,  assert_result_count, with_tempfile
from ...tests.utils import with_tree
from ...tests.utils import serve_path_via_http
from ...tests.utils import swallow_outputs


def test_download_url_exceptions():
    res0 = download_url(['url1', 'url2'], path=__file__, on_failure='ignore')
    assert_result_count(res0, 1, status='error')
    assert_message('When specifying multiple urls, --path should point to '
                   'an existing directory. Got %r',
                   res0)

    res1 = download_url('http://example.com/bogus', on_failure='ignore')
    assert_result_count(res1, 1, status='error')
    assert_in('http://example.com/bogus', res1[0]['message'])


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

    out1 = download_url(urls[0], path=outdir)
    assert_result_count(out1, 1)
    eq_(out1[0]['path'], outfiles[0])

    # can't overwrite
    out2 = download_url(urls, path=outdir, on_failure='ignore')
    assert_result_count(out2, 1, status='error')
    assert_in('file1.txt already exists', out2[0]['message'])
    assert_result_count(out2, 1, status='ok')  # only 2nd one
    eq_(out2[1]['path'], outfiles[1])

    out3 = download_url(urls, path=outdir, overwrite=True, on_failure='ignore')
    assert_result_count(out3, 2, status='ok')
    eq_([r['path'] for r in out3], outfiles)
