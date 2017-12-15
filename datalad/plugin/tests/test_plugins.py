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


from datalad.tests.utils import known_failure_direct_mode

import os
import logging
from os.path import join as opj
from os.path import exists
from mock import patch

from datalad.api import plugin
from datalad.api import create
from datalad import cfg

from datalad.tests.utils import swallow_logs
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import chpwd
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git

broken_plugin = """garbage"""

nodocs_plugin = """\
def dlplugin():
    pass
"""

# functioning plugin dummy
dummy_plugin = '''\
"""real dummy"""

def dlplugin(dataset, noval, withval='test'):
    "mydocstring"
    yield dict(
        status='ok',
        action='dummy',
        args=dict(
            dataset=dataset,
            noval=noval,
            withval=withval))
'''


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

    def fake_is_installed(*args, **kwargs):
        return True
    with patch('datalad.plugin._get_plugins', return_value=fake_dummy_spec), \
        patch('datalad.distribution.dataset.Dataset.is_installed', return_value=True):
        # does not trip over unsupported argument, they get filtered out, because
        # we carry all kinds of stuff
        with swallow_logs(new_level=logging.WARNING) as cml:
            res = list(plugin(['dummy', 'noval=one', 'obscure=some']))
            assert_status('ok', res)
            cml.assert_logged(
                msg=".*ignoring plugin argument\\(s\\).*obscure.*, not supported by plugin.*",
                regex=True, level='WARNING')
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


@with_tempfile(mkdir=True)
def test_plugin_config(path):
    # baseline behavior, empty datasets on create
    ds = create(dataset=opj(path, 'ds1'))
    eq_(sorted(os.listdir(ds.path)), ['.datalad', '.git', '.gitattributes'])
    # now we configure a plugin to run twice after `create`
    cfg.add('datalad.create.run-after',
            'add_readme filename=after1.txt',
            where='global')
    cfg.add('datalad.create.run-after',
            'add_readme filename=after2.txt',
            where='global')
    # force reload to pick up newly populated .gitconfig
    cfg.reload(force=True)
    assert_in('datalad.create.run-after', cfg)
    # and now we create a dataset and expect the two readme files
    # to be part of it
    ds = create(dataset=opj(path, 'ds'))
    ok_clean_git(ds.path)
    assert(exists(opj(ds.path, 'after1.txt')))
    assert(exists(opj(ds.path, 'after2.txt')))
    # cleanup
    cfg.unset(
        'datalad.create.run-after',
        where='global')
    assert_not_in('datalad.create.run-after', cfg)


@with_tempfile(mkdir=True)
def test_wtf(path):
    # smoke test for now
    with swallow_outputs() as cmo:
        plugin(['wtf'], dataset=path)
        assert_not_in('Dataset information', cmo.out)
        assert_in('Configuration', cmo.out)
    with chpwd(path):
        with swallow_outputs() as cmo:
            plugin(['wtf'])
            assert_not_in('Dataset information', cmo.out)
            assert_in('Configuration', cmo.out)
    # now with a dataset
    ds = create(path)
    with swallow_outputs() as cmo:
        plugin(['wtf'], dataset=ds.path)
        assert_in('Configuration', cmo.out)
        assert_in('Dataset information', cmo.out)
        assert_in('path: {}'.format(ds.path), cmo.out)


@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_no_annex(path):
    ds = create(path)
    ok_clean_git(ds.path)
    create_tree(
        ds.path,
        {'code': {
            'inannex': 'content',
            'notinannex': 'othercontent'}})
    # add two files, pre and post configuration
    ds.add(opj('code', 'inannex'))
    plugin(['no_annex', 'pattern=code/**'], dataset=ds)
    ds.add(opj('code', 'notinannex'))
    ok_clean_git(ds.path)
    # one is annex'ed, the other is not, despite no change in add call
    # importantly, also .gitattribute is not annexed
    eq_([opj('code', 'inannex')],
        ds.repo.get_annexed_files())
