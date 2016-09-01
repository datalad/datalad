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
from datalad.support.dsconfig import ConfigManager
from datalad.cmd import CommandError

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
        cfg.get('something', 'user'),
        ('name=Jane Doe', 'email=jd@example.com'))
    assert_raises(KeyError, cfg.get, 'somedthing', 'user')
    assert_equal(cfg.getfloat('onemore.complicated の beast with.dot', 'findme'), 5.0)
    assert_equal(cfg.getint('something', 'myint'), 3)

    # gitpython-style access
    assert_equal(cfg.get('something', 'myint'), cfg.get_value('something', 'myint'))
    assert_equal(cfg.get_value('doesnot', 'exist', default='oohaaa'), 'oohaaa')
    # weired, but that is how it is
    assert_raises(KeyError, cfg.get_value, 'doesnot', 'exist', default=None)

    # modification follows
    cfg.add('something.new', 'の')
    assert_equal(cfg.get('something', 'new'), 'の')
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

    # fails unkown location
    assert_raises(ValueError, cfg.add, 'somesuch', 'shit', where='umpalumpa')

    # very carefully test non-local config
    # so carefully that even in case of bad weather Yarik doesn't find some
    # lame datalad unittest sections in his precious ~/.gitconfig
    with patch.dict('os.environ', {'HOME': new_home}):
        global_gitconfig = opj(new_home, '.gitconfig')
        assert(not exists(global_gitconfig))
        globalcfg = ConfigManager(dataset_only=False)
        assert_not_in('datalad.unittest.youcan', globalcfg)
        cfg.add('datalad.unittest.youcan', 'removeme', where='global')
        assert(exists(global_gitconfig))
        # it did not go into the dataset's config!
        assert_not_in('datalad.unittest.youcan', cfg)
        # does not monitor changes!
        globalcfg.reload()
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
