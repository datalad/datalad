# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj

from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines
from ...nodes.annex import initiate_dataset
from ....utils import chpwd
from ....utils import _path_
from ....tests.utils import with_tree
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import with_tempfile
from ....tests.utils import serve_path_via_http
from ....tests.utils import ok_file_has_content
from ....tests.utils import ok_file_under_git
from ..simple_with_archives import pipeline

from datalad.api import crawl

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


def test_smoke_pipelines():
    yield _test_smoke_pipelines, pipeline, ["random_url"]

from .test_balsa import TEST_TREE1

# A little integration test

@with_tree(tree=TEST_TREE1, archives_leading_dir=False)
@serve_path_via_http
@with_tempfile
def test_simple1(ind, topurl, outd):

    list(initiate_dataset(
        template="simple_with_archives",
        dataset_name='test1',
        path=outd,
        add_fields={'url': topurl + 'study/show/WG33',
                    'a_href_match_': '.*download.*'}
    )({}))

    with chpwd(outd):
        out, stats = crawl()

    eq_(stats.add_annex, 3)

    ok_file_under_git(outd, 'file1.nii', annexed=True)
    ok_file_has_content(opj(outd, 'file1.nii'), 'content of file1.nii')

    ok_file_under_git(outd, _path_('dir1/file2.nii'), annexed=True)
    ok_file_has_content(opj(outd, 'dir1', 'file2.nii'), 'content of file2.nii')

    eq_(len(out), 1)

