# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from nose.tools import eq_, assert_raises
from ...api import crawl_init
from os import remove
from os.path import exists
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, chpwd
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR


# TODO: generalize 3 first tests into 1 parametric... reference git grep 'yield_test'


@with_tempfile(mkdir=True)
def test_crawl_init_openfmri(tmpdir):
    ar = AnnexRepo(tmpdir)
    with chpwd(tmpdir):
        crawl_init(template='openfmri', template_func='superdataset_pipeline')
        eq_(exists(CRAWLER_META_DIR), True)
        eq_(exists(CRAWLER_META_CONFIG_PATH), True)
        f = open(CRAWLER_META_CONFIG_PATH, 'r')
        contents = f.read()
        eq_(contents, '[crawl:pipeline]\ntemplate = openfmri\nfunc = superdataset_pipeline\n\n')


@with_tempfile(mkdir=True)
def test_crawl_init_args_dict(tmpdir):
    ar = AnnexRepo(tmpdir)
    with chpwd(tmpdir):
        crawl_init({'dataset': 'ds000001'}, template='openfmri')
        eq_(exists(CRAWLER_META_DIR), True)
        eq_(exists(CRAWLER_META_CONFIG_PATH), True)
        f = open(CRAWLER_META_CONFIG_PATH, 'r')
        contents = f.read()
        eq_(contents, '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n\n')


@with_tempfile(mkdir=True)
def test_crawl_init_args_list(tmpdir):
    ar = AnnexRepo(tmpdir)
    with chpwd(tmpdir):
        crawl_init(['dataset=ds000001', 'versioned_urls=True'], template='openfmri')
        eq_(exists(CRAWLER_META_DIR), True)
        eq_(exists(CRAWLER_META_CONFIG_PATH), True)
        f = open(CRAWLER_META_CONFIG_PATH, 'r')
        contents = f.read()
        eq_(contents, '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n_versioned_urls = True\n\n')


@with_tempfile(mkdir=True)  # passes
def test_crawl_init_error(tmpdir):
    ar = AnnexRepo(tmpdir)
    with chpwd(tmpdir):
        assert_raises(ValueError, crawl_init, args=tmpdir)


@with_tempfile(mkdir=True)
def test_crawl_init_wrong_args(tmpdir):
    ar = AnnexRepo(tmpdir, create=True)
    with chpwd(tmpdir):
        # incorrect argument -- should blow
        assert_raises(RuntimeError, crawl_init, ['dataset=Baltimore', 'pie=True'], template='openfmri')
