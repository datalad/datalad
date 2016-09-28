# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


from nose.tools import eq_, assert_raises, assert_in
from mock import patch
from ...api import crawl_init
from collections import OrderedDict
from os.path import exists
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, chpwd
from datalad.tests.utils import ok_clean_git
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR
from datalad.distribution.dataset import Dataset


@with_tempfile(mkdir=True)
def _test_crawl_init(args, template, template_func, save, target_value, tmpdir):
    ar = AnnexRepo(tmpdir, create=True)
    with chpwd(tmpdir):
        crawl_init(args=args, template=template, template_func=template_func, save=save)
        eq_(exists(CRAWLER_META_DIR), True)
        eq_(exists(CRAWLER_META_CONFIG_PATH), True)
        f = open(CRAWLER_META_CONFIG_PATH, 'r')
        contents = f.read()
        eq_(contents, target_value)
        if save:
            ds = Dataset(tmpdir)
            ok_clean_git(tmpdir, annex=isinstance(ds.repo, AnnexRepo))


def test_crawl_init():
    yield _test_crawl_init, None, 'openfmri', 'superdataset_pipeline', False, \
          '[crawl:pipeline]\ntemplate = openfmri\nfunc = superdataset_pipeline\n\n'
    yield _test_crawl_init, {'dataset': 'ds000001'}, 'openfmri', None, False, \
          '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n\n'
    yield _test_crawl_init, ['dataset=ds000001', 'versioned_urls=True'], 'openfmri', None, False, \
          '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n_versioned_urls = True\n\n'
    yield _test_crawl_init, None, 'openfmri', 'superdataset_pipeline', True, \
          '[crawl:pipeline]\ntemplate = openfmri\nfunc = superdataset_pipeline\n\n'


@with_tempfile(mkdir=True)
def _test_crawl_init_error(args, template, template_func, target_value, tmpdir):
        ar = AnnexRepo(tmpdir)
        with chpwd(tmpdir):
            assert_raises(target_value, crawl_init, args=args, template=template, template_func=template_func)


def test_crawl_init_error():
    yield _test_crawl_init_error, 'tmpdir', None, None, ValueError
    yield _test_crawl_init_error, ['dataset=Baltimore', 'pie=True'], 'openfmri', None, RuntimeError
    yield _test_crawl_init_error, None, None, None, TypeError


@with_tempfile(mkdir=True)
def _test_crawl_init_error_patch(return_value, exc, exc_msg, d):

    ar = AnnexRepo(d, create=True)
    with patch('datalad.interface.crawl_init.load_pipeline_from_template',
               return_value=lambda dataset: return_value) as cm:
        with chpwd(d):
            with assert_raises(exc) as cm2:
                crawl_init(args=['dataset=Baltimore'], template='openfmri')
            assert_in(exc_msg, str(cm2.exception))

            cm.assert_called_with('openfmri', None, return_only=True, kwargs=OrderedDict([('dataset', 'Baltimore')]))


def test_crawl_init_error_patch():
    yield _test_crawl_init_error_patch, [], ValueError, "returned pipeline is empty"
    yield _test_crawl_init_error_patch, {1: 2}, ValueError, "pipeline should be represented as a list. Got: {1: 2}"



