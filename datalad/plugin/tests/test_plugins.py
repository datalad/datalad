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

from datalad.coreapi import create
from datalad.coreapi import Dataset
from datalad.api import wtf
from datalad.api import no_annex
from datalad import cfg

from datalad.tests.utils import swallow_logs
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import chpwd
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import skip_if

has_bids_extractor = False

broken_plugin = """garbage"""

nodocs_plugin = """\
def dlplugin():
    yield
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


# TODO bring back when functionality is back
#@with_tempfile(mkdir=True)
#def test_plugin_config(path):
#    # baseline behavior, empty datasets on create
#    ds = create(dataset=opj(path, 'ds1'))
#    eq_(sorted(os.listdir(ds.path)), ['.datalad', '.git', '.gitattributes'])
#    # now we configure a plugin to run twice after `create`
#    cfg.add('datalad.create.run-after',
#            'add_readme filename=after1.txt',
#            where='global')
#    cfg.add('datalad.create.run-after',
#            'add_readme filename=after2.txt',
#            where='global')
#    # force reload to pick up newly populated .gitconfig
#    cfg.reload(force=True)
#    assert_in('datalad.create.run-after', cfg)
#    # and now we create a dataset and expect the two readme files
#    # to be part of it
#    ds = create(dataset=opj(path, 'ds'))
#    ok_clean_git(ds.path)
#    assert(exists(opj(ds.path, 'after1.txt')))
#    assert(exists(opj(ds.path, 'after2.txt')))
#    # cleanup
#    cfg.unset(
#        'datalad.create.run-after',
#        where='global')
#    assert_not_in('datalad.create.run-after', cfg)


@with_tempfile(mkdir=True)
def test_wtf(path):
    # smoke test for now
    with swallow_outputs() as cmo:
        wtf(dataset=path)
        assert_not_in('Dataset information', cmo.out)
        assert_in('Configuration', cmo.out)
    with chpwd(path):
        with swallow_outputs() as cmo:
            wtf()
            assert_not_in('Dataset information', cmo.out)
            assert_in('Configuration', cmo.out)
    # now with a dataset
    ds = create(path)
    with swallow_outputs() as cmo:
        wtf(dataset=ds.path)
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
    no_annex(pattern='code/**', dataset=ds)
    ds.add(opj('code', 'notinannex'))
    ok_clean_git(ds.path)
    # one is annex'ed, the other is not, despite no change in add call
    # importantly, also .gitattribute is not annexed
    eq_([opj('code', 'inannex')],
        ds.repo.get_annexed_files())
