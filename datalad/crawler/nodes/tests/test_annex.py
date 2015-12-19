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
from ..annex import Annexificator
from ....tests.utils import assert_equal, assert_in
from ....tests.utils import with_tree, serve_path_via_http
from ....tests.utils import ok_file_under_git
from ....tests.utils import ok_file_has_content
from ...pipeline import load_pipeline_from_config
from ....consts import CRAWLER_META_CONFIG_PATH

@with_tempfile(mkdir=True)
def test_initialize_handle(path):
    handle_path = opj(path, 'test')
    datas = list(initiate_handle('template', 'testhandle', path=handle_path)())
    assert_equal(len(datas), 1)
    data = datas[0]
    eq_(data['handle_path'], handle_path)
    crawl_cfg = opj(handle_path, CRAWLER_META_CONFIG_PATH)
    ok_(exists, crawl_cfg)
    pipeline = load_pipeline_from_config(crawl_cfg)
    raise SkipTest("TODO much more")

@with_tree(tree=[
    ('d1', (
        ('1.dat', '1.dat load'),
    ))
])
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_annex_file(topdir, topurl, outdir):
    annex = Annexificator(path=outdir, options=["-c", "annex.largefiles=exclude=*.txt"])

    input = {'url': "%sd1/1.dat" % topurl, 'filename': '1-copy.dat'}
    tfile = opj(outdir, '1-copy.dat')
    expected_output = [input.copy()]   # nothing to be added/changed
    output = list(annex(input))
    assert_equal(output, expected_output)
    ok_file_under_git(tfile, annexed=True)
    ok_file_has_content(tfile, '1.dat load')
    whereis = annex.repo.annex_whereis(tfile)
    assert_in("web", whereis)  # url must have been added
    assert_equal(len(whereis), 2)
    # TODO: check the url

    input = {'url': "%sd1/1.dat" % topurl, 'filename': '1.txt'}
    tfile = opj(outdir, '1.txt')
    output = list(annex(input))
    ok_file_under_git(tfile, annexed=False)
    ok_file_has_content(tfile, '1.dat load')
