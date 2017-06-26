# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test plugin interface mechanics"""


import logging
from os.path import join as opj
from mock import patch

from datalad.api import plugin
from datalad.api import create

from datalad.tests.utils import swallow_logs
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import chpwd
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_status
from datalad.tests.utils import eq_

broken_plugin = """garbage"""

nodocs_plugin = """\
def datalad_plugin():
    pass
"""

# functioning plugin dummy
dummy_plugin = """\
#PLUGINSYNOPSIS: real dummy

def datalad_plugin(dataset, noval, withval='test'):
    "mydocstring"
    yield dict(
        status='ok',
        action='dummy',
        args=dict(
            dataset=dataset,
            noval=noval,
            withval=withval))
"""


@with_tempfile()
@with_tempfile(mkdir=True)
def test_plugin_call(path, dspath):
    # make plugins
    create_tree(
        path,
        {
            'dlplugin_dummy.py': dummy_plugin,
            'dlplugin_nodocs.py': nodocs_plugin,
            'dlplugin_broken.py': broken_plugin,
        })
    fake_dummy_spec = {
        'dummy': {'file': opj(path, 'dlplugin_dummy.py')},
        'nodocs': {'file': opj(path, 'dlplugin_nodocs.py')},
        'broken': {'file': opj(path, 'dlplugin_broken.py')},
    }

    with patch('datalad.plugin._get_plugins', return_value=fake_dummy_spec):
        with swallow_outputs() as cmo:
            plugin(showplugininfo=True)
            # hyphen spacing depends on the longest plugin name!
            # sorted
            # summary list generation doesn't actually load plugins for speed,
            # hence broken is not known to be broken here
            eq_(cmo.out,
                "broken [no synopsis] ({})\ndummy  - real dummy ({})\nnodocs [no synopsis] ({})\n".format(
                    fake_dummy_spec['broken']['file'],
                    fake_dummy_spec['dummy']['file'],
                    fake_dummy_spec['nodocs']['file']))
        with swallow_outputs() as cmo:
            plugin(['dummy'], showpluginhelp=True)
            eq_(cmo.out.rstrip(), "mydocstring")
        with swallow_outputs() as cmo:
            plugin(['nodocs'], showpluginhelp=True)
            eq_(cmo.out.rstrip(), "This plugin has no documentation")
        # loading fails, no docs
        assert_raises(ValueError, plugin, ['broken'], showpluginhelp=True)

    # assume this most obscure plugin name is not used
    assert_raises(ValueError, plugin, '32sdfhvz984--^^')

    # broken plugin argument, must match Python keyword arg
    # specs
    assert_raises(ValueError, plugin, ['dummy', '1245'])

    with patch('datalad.plugin._get_plugins', return_value=fake_dummy_spec):
        # does not trip over unsupported argument, they get filtered out, because
        # we carry all kinds of stuff
        with swallow_logs(new_level=logging.WARNING) as cml:
            res = list(plugin(['dummy', 'noval=one', 'obscure=some']))
            assert_status('ok', res)
            cml.assert_logged(
                msg="ignoring plugin argument(s) {'obscure'}, not supported by plugin",
                regex=False, level='WARNING')
        # fails on missing positional arg
        assert_raises(TypeError, plugin, ['dummy'])
        # positional and kwargs actually make it into the plugin
        res = list(plugin(['dummy', 'noval=one', 'withval=two']))[0]
        eq_('one', res['args']['noval'])
        eq_('two', res['args']['withval'])
        # kwarg defaults are preserved
        res = list(plugin(['dummy', 'noval=one']))[0]
        eq_('test', res['args']['withval'])
        # repeated specification yields list input
        res = list(plugin(['dummy', 'noval=one', 'noval=two']))[0]
        eq_(['one', 'two'], res['args']['noval'])
        # can do the same thing  while bypassing argument parsing for calls
        # from within python, and even preserve native python dtypes
        res = list(plugin(['dummy', ('noval', 1), ('noval', 'two')]))[0]
        eq_([1, 'two'], res['args']['noval'])
        # and we can further simplify in this case by passing lists right
        # away
        res = list(plugin(['dummy', ('noval', [1, 'two'])]))[0]
        eq_([1, 'two'], res['args']['noval'])

    # dataset arg handling
    # run plugin that needs a dataset where there is none
    with patch('datalad.plugin._get_plugins', return_value=fake_dummy_spec):
        ds = None
        with chpwd(dspath):
            assert_raises(ValueError, plugin, ['dummy', 'noval=one'])
            # create a dataset here, fixes the error
            ds = create()
            print(ds.path, dspath)
            res = list(plugin(['dummy', 'noval=one']))[0]
            # gives dataset instance
            eq_(ds, res['args']['dataset'])
        # no do again, giving the dataset path
        # but careful, `dataset` is a proper argument
        res = list(plugin(['dummy', 'noval=one'], dataset=dspath))[0]
        eq_(ds, res['args']['dataset'])
        # however, if passed alongside the plugins args it also works
        res = list(plugin(['dummy', 'dataset={}'.format(dspath), 'noval=one']))[0]
        eq_(ds, res['args']['dataset'])
        # but if both are given, the proper args takes precedence
        assert_raises(ValueError, plugin, ['dummy', 'dataset={}'.format(dspath), 'noval=one'],
                      dataset='rubbish')
