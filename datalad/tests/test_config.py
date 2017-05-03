# ex: set sts=4 ts=4 sw=4 noet:
# -*- coding: utf-8 -*-
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

import os
from os.path import exists
from os.path import join as opj

from mock import patch
from nose.tools import assert_false, assert_true, assert_equal
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in, assert_not_in
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.utils import swallow_logs

from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.config import ConfigManager
from datalad.cmd import CommandError

from datalad.tests.utils import with_testsui

# XXX tabs are intentional (part of the format)!
# XXX put back! confuses pep8
_config_file_content = """\
[something]
user = name=Jane Doe
user = email=jd@example.com
myint = 3

[onemore "complicated の beast with.dot"]
findme = 5.0
"""

_dataset_config_template = {
    'ds': {
        '.datalad': {
            'config': _config_file_content}}}


@with_tree(tree=_dataset_config_template)
@with_tempfile(mkdir=True)
def test_something(path, new_home):
    # read nothing, has nothing
    cfg = ConfigManager(dataset_only=True)
    assert_false(len(cfg))
    # now read the example config
    cfg = ConfigManager(Dataset(opj(path, 'ds')), dataset_only=True)
    assert_equal(len(cfg), 3)
    assert_in('something.user', cfg)
    # multi-value
    assert_equal(len(cfg['something.user']), 2)
    assert_equal(cfg['something.user'], ('name=Jane Doe', 'email=jd@example.com'))

    assert_true(cfg.has_section('something'))
    assert_false(cfg.has_section('somethingelse'))
    assert_equal(sorted(cfg.sections()), ['onemore.complicated の beast with.dot', 'something'])
    assert_true(cfg.has_option('something', 'user'))
    assert_false(cfg.has_option('something', 'us?er'))
    assert_false(cfg.has_option('some?thing', 'user'))
    assert_equal(sorted(cfg.options('something')), ['myint', 'user'])
    assert_equal(cfg.options('onemore.complicated の beast with.dot'), ['findme'])

    assert_equal(
        sorted(cfg.items()),
        [('onemore.complicated の beast with.dot.findme', '5.0'),
         ('something.myint', '3'),
         ('something.user', ('name=Jane Doe', 'email=jd@example.com'))])
    assert_equal(
        sorted(cfg.items('something')),
        [('something.myint', '3'),
         ('something.user', ('name=Jane Doe', 'email=jd@example.com'))])

    # always get all values
    assert_equal(
        cfg.get('something.user'),
        ('name=Jane Doe', 'email=jd@example.com'))
    assert_raises(KeyError, cfg.__getitem__, 'somedthing.user')
    assert_equal(cfg.getfloat('onemore.complicated の beast with.dot', 'findme'), 5.0)
    assert_equal(cfg.getint('something', 'myint'), 3)
    assert_equal(cfg.getbool('something', 'myint'), True)
    assert_equal(cfg.getbool('doesnot', 'exist', default=True), True)
    assert_raises(TypeError, cfg.getbool, 'something', 'user')

    # gitpython-style access
    assert_equal(cfg.get('something.myint'), cfg.get_value('something', 'myint'))
    assert_equal(cfg.get_value('doesnot', 'exist', default='oohaaa'), 'oohaaa')
    # weired, but that is how it is
    assert_raises(KeyError, cfg.get_value, 'doesnot', 'exist', default=None)

    # modification follows
    cfg.add('something.new', 'の')
    assert_equal(cfg.get('something.new'), 'の')
    # sections are added on demand
    cfg.add('unheard.of', 'fame')
    assert_true(cfg.has_section('unheard.of'))
    comp = cfg.items('something')
    cfg.rename_section('something', 'this')
    assert_true(cfg.has_section('this'))
    assert_false(cfg.has_section('something'))
    # direct comparision would fail, because of section prefix
    assert_equal(len(cfg.items('this')), len(comp))
    # fail if no such section
    with swallow_logs():
        assert_raises(CommandError, cfg.rename_section, 'nothere', 'irrelevant')
    assert_true(cfg.has_option('this', 'myint'))
    cfg.unset('this.myint')
    assert_false(cfg.has_option('this', 'myint'))

    # batch a changes
    cfg.add('mike.wants.to', 'know', reload=False)
    assert_false('mike.wants.to' in cfg)
    cfg.add('mike.wants.to', 'eat')
    assert_true('mike.wants.to' in cfg)
    assert_equal(len(cfg['mike.wants.to']), 2)

    # set a new one:
    cfg.set('mike.should.have', 'known')
    assert_in('mike.should.have', cfg)
    assert_equal(cfg['mike.should.have'], 'known')
    # set an existing one:
    cfg.set('mike.should.have', 'known better')
    assert_equal(cfg['mike.should.have'], 'known better')
    # set, while there are several matching ones already:
    cfg.add('mike.should.have', 'a meal')
    assert_equal(len(cfg['mike.should.have']), 2)
    # raises with force=False
    assert_raises(CommandError,
                  cfg.set, 'mike.should.have', 'a beer', force=False)
    assert_equal(len(cfg['mike.should.have']), 2)
    # replaces all matching ones with force=True
    cfg.set('mike.should.have', 'a beer', force=True)
    assert_equal(cfg['mike.should.have'], 'a beer')

    # fails unknown location
    assert_raises(ValueError, cfg.add, 'somesuch', 'shit', where='umpalumpa')

    # very carefully test non-local config
    # so carefully that even in case of bad weather Yarik doesn't find some
    # lame datalad unittest sections in his precious ~/.gitconfig
    with patch.dict('os.environ',
                    {'HOME': new_home, 'DATALAD_SNEAKY_ADDITION': 'ignore'}):
        global_gitconfig = opj(new_home, '.gitconfig')
        assert(not exists(global_gitconfig))
        globalcfg = ConfigManager(dataset_only=False)
        assert_not_in('datalad.unittest.youcan', globalcfg)
        assert_in('datalad.sneaky.addition', globalcfg)
        cfg.add('datalad.unittest.youcan', 'removeme', where='global')
        assert(exists(global_gitconfig))
        # it did not go into the dataset's config!
        assert_not_in('datalad.unittest.youcan', cfg)
        # does not monitor additions!
        globalcfg.reload(force=True)
        assert_in('datalad.unittest.youcan', globalcfg)
        with swallow_logs():
            assert_raises(
                CommandError,
                globalcfg.unset,
                'datalad.unittest.youcan',
                where='local')
        assert(globalcfg.has_section('datalad.unittest'))
        globalcfg.unset('datalad.unittest.youcan', where='global')
        # but after we unset the only value -- that section is no longer listed
        assert (not globalcfg.has_section('datalad.unittest'))
        assert_not_in('datalad.unittest.youcan', globalcfg)
        # although it does leaves empty section behind in the file
        ok_file_has_content(global_gitconfig, '[datalad "unittest"]', strip=True)
        # remove_section to clean it up entirely
        globalcfg.remove_section('datalad.unittest', where='global')
        ok_file_has_content(global_gitconfig, "")

    cfg = ConfigManager(
        Dataset(opj(path, 'ds')),
        dataset_only=True,
        overrides={'datalad.godgiven': True})
    assert_equal(cfg.get('datalad.godgiven'), True)
    # setter has no effect
    cfg.set('datalad.godgiven', 'false')
    assert_equal(cfg.get('datalad.godgiven'), True)


@with_tree(tree={
    'ds': {
        '.datalad': {
            'config': """\
[crazy]
    fa = !git remote | xargs -r -I REMOTE /bin/bash -c 'echo I: Fetching from REMOTE && git fetch --prune REMOTE && git fetch -t REMOTE' && [ -d .git/svn ] && bash -c 'echo I: Fetching from SVN && git svn fetch' || : && [ -e .gitmodules ] && bash -c 'echo I: Fetching submodules && git submodule foreach git fa' && [ -d .git/sd ] && bash -c 'echo I: Fetching bugs into sd && git-sd pull --all' || :
    pa = !git paremotes | tr ' ' '\\n'  | xargs -r -l1 git push
    pt = !git testremotes | tr ' ' '\\n'  | xargs -r -l1 -I R git push -f R master
    ptdry = !git testremotes | tr ' ' '\\n'  | xargs -r -l1 -I R git push -f --dry-run R master
    padry = !git paremotes | tr ' ' '\\n' | xargs -r -l1 git push --dry-run
"""}}})
def test_crazy_cfg(path):
    cfg = ConfigManager(Dataset(opj(path, 'ds')), dataset_only=True)
    assert_in('crazy.padry', cfg)


@with_tempfile
def test_obtain(path):
    ds = create(path)
    cfg = ConfigManager(ds)
    dummy = 'datalad.test.dummy'
    # we know nothing and we don't know how to ask
    assert_raises(RuntimeError, cfg.obtain, dummy)
    # can report known ones
    cfg.add(dummy, '5.3')
    assert_equal(cfg.obtain(dummy), '5.3')
    # better type
    assert_equal(cfg.obtain(dummy, valtype=float), 5.3)
    # don't hide type issues, float doesn't become an int magically
    assert_raises(ValueError, cfg.obtain, dummy, valtype=int)
    # inject some prior knowledge
    from datalad.interface.common_cfg import definitions as cfg_defs
    cfg_defs[dummy] = dict(type=float)
    # no we don't need to specify a type anymore
    assert_equal(cfg.obtain(dummy), 5.3)
    # but if we remove the value from the config, all magic is gone
    cfg.unset(dummy)
    # we know nothing and we don't know how to ask
    assert_raises(RuntimeError, cfg.obtain, dummy)

    #
    # test actual interaction
    #
    @with_testsui()
    def ask():
        # fail on unkown dialog type
        assert_raises(ValueError, cfg.obtain, dummy, dialog_type='Rorschach_test')
    ask()

    # ask nicely, and get a value of proper type using the preconfiguration
    @with_testsui(responses='5.3')
    def ask():
        assert_equal(
            cfg.obtain(dummy, dialog_type='question', text='Tell me'), 5.3)
    ask()

    # preconfigure even more, to get the most compact call
    cfg_defs[dummy]['ui'] = ('question', dict(text='tell me', title='Gretchen Frage'))

    @with_testsui(responses='5.3')
    def ask():
        assert_equal(cfg.obtain(dummy), 5.3)
    ask()

    @with_testsui(responses='murks')
    def ask():
        assert_raises(ValueError, cfg.obtain, dummy)
    ask()

    # fail to store when destination is not specified, will not even ask
    @with_testsui()
    def ask():
        assert_raises(ValueError, cfg.obtain, dummy, store=True)
    ask()

    # but we can preconfigure it
    cfg_defs[dummy]['destination'] = 'broken'

    @with_testsui(responses='5.3')
    def ask():
        assert_raises(ValueError, cfg.obtain, dummy, store=True)
    ask()

    # fixup destination
    cfg_defs[dummy]['destination'] = 'dataset'

    @with_testsui(responses='5.3')
    def ask():
        assert_equal(cfg.obtain(dummy, store=True), 5.3)
    ask()

    # now it won't have to ask again
    @with_testsui()
    def ask():
        assert_equal(cfg.obtain(dummy), 5.3)
    ask()

    # wipe it out again
    cfg.unset(dummy)
    assert_not_in(dummy, cfg)

    # XXX cannot figure out how I can simulate a simple <Enter>
    ## respond with accepting the default
    #@with_testsui(responses=...)
    #def ask():
    #    assert_equal(cfg.obtain(dummy, default=5.3), 5.3)
    #ask()


def test_from_env():
    cfg = ConfigManager()
    assert_not_in('datalad.crazy.cfg', cfg)
    os.environ['DATALAD_CRAZY_CFG'] = 'impossibletoguess'
    cfg.reload()
    assert_in('datalad.crazy.cfg', cfg)
    assert_equal(cfg['datalad.crazy.cfg'], 'impossibletoguess')
    # not in dataset-only mode
    cfg = ConfigManager(Dataset('nowhere'), dataset_only=True)
    assert_not_in('datalad.crazy.cfg', cfg)
    # check env trumps override
    cfg = ConfigManager()
    assert_not_in('datalad.crazy.override', cfg)
    cfg.overrides['datalad.crazy.override'] = 'fromoverride'
    cfg.reload()
    assert_equal(cfg['datalad.crazy.override'], 'fromoverride')
    os.environ['DATALAD_CRAZY_OVERRIDE'] = 'fromenv'
    cfg.reload()
    assert_equal(cfg['datalad.crazy.override'], 'fromenv')
