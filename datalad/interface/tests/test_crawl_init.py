# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from nose.tools import eq_
from ...api import crawl_init
from os.path import exists, curdir
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR
from datalad.crawler.pipeline import initiate_pipeline_config
from datalad.crawler.pipeline import load_pipeline_from_template


def test_crawl_init():
    crawl_init(template='openfmri', template_func='superdataset_pipeline')
    eq_(exists(CRAWLER_META_DIR), True)
    eq_(exists(CRAWLER_META_CONFIG_PATH), True)
    f = open(CRAWLER_META_CONFIG_PATH, 'r')
    contents = f.read()
    eq_(contents, '[crawl:pipeline]\ntemplate = openfmri\nfunc = superdataset_pipeline\n\n')

    # template_kwargs given as a dict
    crawl_init(template='fcptable', template_kwargs={'dataset': 'Baltimore', 'tarballs': 'True'})
    eq_(exists(CRAWLER_META_DIR), True)
    eq_(exists(CRAWLER_META_CONFIG_PATH), True)
    f = open(CRAWLER_META_CONFIG_PATH, 'r')
    contents = f.read()
    eq_(contents, '[crawl:pipeline]\ntemplate = fcptable\n_dataset = Baltimore\n_tarballs = True\n\n')

    # template_kwargs given as a list
    crawl_init(template='fcptable', template_kwargs=['dataset=Baltimore', 'tarballs=True'])
    eq_(exists(CRAWLER_META_DIR), True)
    eq_(exists(CRAWLER_META_CONFIG_PATH), True)
    f = open(CRAWLER_META_CONFIG_PATH, 'r')
    contents = f.read()
    eq_(contents, '[crawl:pipeline]\ntemplate = fcptable\n_dataset = Baltimore\n_tarballs = True\n\n')




