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

import logging
import os
from os.path import exists
from os.path import join as opj

from unittest.mock import patch
from datalad.tests.utils import (
    assert_equal,
    assert_false,
    assert_in,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_true,
    chpwd,
    ok_file_has_content,
    with_tempfile,
    with_testsui,
    with_tree,
)
from datalad.utils import (
    get_home_envvars,
    swallow_logs,
    Path
)

from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.config import (
    ConfigManager,
    parse_gitconfig_dump,
    rewrite_url,
    write_config_section,
)
from datalad.cmd import CommandError

from datalad.support.gitrepo import GitRepo
from datalad import cfg as dl_cfg


# XXX tabs are intentional (part of the format)!
# XXX put back! confuses pep8
_config_file_content = """\
[something]
user = name=Jane Doe
user = email=jd@example.com
novalue
empty =
myint = 3

[onemore "complicated の beast with.dot"]
findme = 5.0
"""

gitcfg_dump = """\
core.withdot
true\0just.a.key\0annex.version
8\0filter.with2dots.some
long\ntext with\nnewlines\0annex.something
abcdef\0"""


# include a "command line" origin
gitcfg_dump_w_origin = """\
file:.git/config\0core.withdot
true\0file:.git/config\0just.a.key\0file:/home/me/.gitconfig\0annex.version
8\0file:.git/config\0filter.with2dots.some
long\ntext with\nnewlines\0file:.git/config\0command line:\0annex.something
abcdef\0"""


gitcfg_parsetarget = {
    'core.withdot': 'true',
    'just.a.key': None,
    'annex.version': '8',
    'filter.with2dots.some': 'long\ntext with\nnewlines',
    'annex.something': 'abcdef',
}


_dataset_config_template = {
    'ds': {
        '.datalad': {
            'config': _config_file_content}}}


def test_parse_gitconfig_dump():
    # simple case, no origin info, clean output
    parsed, files = parse_gitconfig_dump(gitcfg_dump)
    assert_equal(files, set())
    assert_equal(gitcfg_parsetarget, parsed)
    # now with origin information in the dump
    parsed, files = parse_gitconfig_dump(gitcfg_dump_w_origin, cwd='ROOT')
    assert_equal(
        files,
        # the 'command line:' origin is ignored
        set((Path('ROOT/.git/config'), Path('/home/me/.gitconfig'))))
    assert_equal(gitcfg_parsetarget, parsed)

    # now contaminate the output with a prepended error message
    # https://github.com/datalad/datalad/issues/5502
    # must work, but really needs the trailing newline
    parsed, files = parse_gitconfig_dump(
        "unfortunate stdout\non more lines\n" + gitcfg_dump_w_origin)
    assert_equal(gitcfg_parsetarget, parsed)


@with_tree(tree=_dataset_config_template)
@with_tempfile(mkdir=True)
def test_something(path, new_home):
    # will refuse to work on dataset without a dataset
    assert_raises(ValueError, ConfigManager, source='dataset')
    # now read the example config
    cfg = ConfigManager(GitRepo(opj(path, 'ds'), create=True), source='dataset')
    assert_equal(len(cfg), 5)
    assert_in('something.user', cfg)
    # multi-value
    assert_equal(len(cfg['something.user']), 2)
    assert_equal(cfg['something.user'], ('name=Jane Doe', 'email=jd@example.com'))

    assert_true(cfg.has_section('something'))
    assert_false(cfg.has_section('somethingelse'))
    assert_equal(sorted(cfg.sections()),
                 [u'onemore.complicated の beast with.dot', 'something'])
    assert_true(cfg.has_option('something', 'user'))
    assert_false(cfg.has_option('something', 'us?er'))
    assert_false(cfg.has_option('some?thing', 'user'))
    assert_equal(sorted(cfg.options('something')), ['empty', 'myint', 'novalue', 'user'])
    assert_equal(cfg.options(u'onemore.complicated の beast with.dot'), ['findme'])

    assert_equal(
        sorted(cfg.items()),
        [(u'onemore.complicated の beast with.dot.findme', '5.0'),
         ('something.empty', ''),
         ('something.myint', '3'),
         ('something.novalue', None),
         ('something.user', ('name=Jane Doe', 'email=jd@example.com'))])
    assert_equal(
        sorted(cfg.items('something')),
        [('something.empty', ''),
         ('something.myint', '3'),
         ('something.novalue', None),
         ('something.user', ('name=Jane Doe', 'email=jd@example.com'))])

    # by default get last value only
    assert_equal(
        cfg.get('something.user'), 'email=jd@example.com')
    # but can get all values
    assert_equal(
        cfg.get('something.user', get_all=True),
        ('name=Jane Doe', 'email=jd@example.com'))
    assert_raises(KeyError, cfg.__getitem__, 'somedthing.user')
    assert_equal(cfg.getfloat(u'onemore.complicated の beast with.dot', 'findme'), 5.0)
    assert_equal(cfg.getint('something', 'myint'), 3)
    assert_equal(cfg.getbool('something', 'myint'), True)
    # git demands a key without value at all to be used as a flag, thus True
    assert_equal(cfg.getbool('something', 'novalue'), True)
    assert_equal(cfg.get('something.novalue'), None)
    # empty value is False
    assert_equal(cfg.getbool('something', 'empty'), False)
    assert_equal(cfg.get('something.empty'), '')
    assert_equal(cfg.getbool('doesnot', 'exist', default=True), True)
    assert_raises(TypeError, cfg.getbool, 'something', 'user')

    # gitpython-style access
    assert_equal(cfg.get('something.myint'), cfg.get_value('something', 'myint'))
    assert_equal(cfg.get_value('doesnot', 'exist', default='oohaaa'), 'oohaaa')
    # weird, but that is how it is
    assert_raises(KeyError, cfg.get_value, 'doesnot', 'exist', default=None)

    # modification follows
    cfg.add('something.new', 'の')
    assert_equal(cfg.get('something.new'), u'の')
    # sections are added on demand
    cfg.add('unheard.of', 'fame')
    assert_true(cfg.has_section('unheard.of'))
    comp = cfg.items('something')
    cfg.rename_section('something', 'this')
    assert_true(cfg.has_section('this'))
    assert_false(cfg.has_section('something'))
    # direct comparison would fail, because of section prefix
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
    env = get_home_envvars(new_home)
    with patch.dict('os.environ',
                    dict(get_home_envvars(new_home), DATALAD_SNEAKY_ADDITION='ignore')):
        global_gitconfig = opj(new_home, '.gitconfig')
        assert(not exists(global_gitconfig))
        globalcfg = ConfigManager()
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
        ok_file_has_content(global_gitconfig, "")

    cfg = ConfigManager(
        Dataset(opj(path, 'ds')),
        source='dataset',
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
    cfg = ConfigManager(GitRepo(opj(path, 'ds'), create=True), source='dataset')
    assert_in('crazy.padry', cfg)
    # make sure crazy config is not read when in local mode
    cfg = ConfigManager(Dataset(opj(path, 'ds')), source='local')
    assert_not_in('crazy.padry', cfg)
    # it will make it in in 'any' mode though
    cfg = ConfigManager(Dataset(opj(path, 'ds')), source='any')
    assert_in('crazy.padry', cfg)
    # typos in the source mode arg will not have silent side-effects
    assert_raises(
        ValueError, ConfigManager, Dataset(opj(path, 'ds')), source='locale')


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
        # fail on unknown dialog type
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
    with patch.dict('os.environ',
                    {'DATALAD_CRAZY_CFG': 'impossibletoguess'}):
        cfg.reload()
        assert_in('datalad.crazy.cfg', cfg)
        assert_equal(cfg['datalad.crazy.cfg'], 'impossibletoguess')
        # not in dataset-only mode
        cfg = ConfigManager(Dataset('nowhere'), source='dataset')
        assert_not_in('datalad.crazy.cfg', cfg)
    # check env trumps override
    cfg = ConfigManager()
    assert_not_in('datalad.crazy.override', cfg)
    cfg.set('datalad.crazy.override', 'fromoverride', where='override')
    cfg.reload()
    assert_equal(cfg['datalad.crazy.override'], 'fromoverride')
    with patch.dict('os.environ',
                    {'DATALAD_CRAZY_OVERRIDE': 'fromenv'}):
        cfg.reload()
        assert_equal(cfg['datalad.crazy.override'], 'fromenv')


def test_from_env_overrides():
    cfg = ConfigManager()
    assert_not_in("datalad.FoO", cfg)

    # Some details, like case and underscores, cannot be handled by the direct
    # environment variable mapping.
    with patch.dict("os.environ",
                    {"DATALAD_FOO": "val"}):
        cfg.reload()
        assert_not_in("datalad.FoO", cfg)
        assert_equal(cfg["datalad.foo"], "val")

    # But they can be handled via DATALAD_CONFIG_OVERRIDES_JSON.
    with patch.dict("os.environ",
                    {"DATALAD_CONFIG_OVERRIDES_JSON": '{"datalad.FoO": "val"}'}):
        cfg.reload()
        assert_equal(cfg["datalad.FoO"], "val")

    # DATALAD_CONFIG_OVERRIDES_JSON isn't limited to datalad variables.
    with patch.dict("os.environ",
                    {"DATALAD_CONFIG_OVERRIDES_JSON": '{"a.b.c": "val"}'}):
        cfg.reload()
        assert_equal(cfg["a.b.c"], "val")

    # Explicitly provided DATALAD_ variables take precedence over those in
    # DATALAD_CONFIG_OVERRIDES_JSON.
    with patch.dict("os.environ",
                    {"DATALAD_CONFIG_OVERRIDES_JSON": '{"datalad.foo": "val"}',
                     "DATALAD_FOO": "val-direct"}):
        cfg.reload()
        assert_equal(cfg["datalad.foo"], "val-direct")

    # JSON decode errors don't lead to crash.
    with patch.dict("os.environ",
                    {"DATALAD_CONFIG_OVERRIDES_JSON": '{'}):
        with swallow_logs(logging.WARNING) as cml:
            cfg.reload()
        assert_in("Failed to load DATALAD_CONFIG_OVERRIDE", cml.out)


def test_overrides():
    cfg = ConfigManager()
    # any sensible (and also our CI) test environment(s) should have this
    assert_in('user.name', cfg)
    # set
    cfg.set('user.name', 'myoverride', where='override')
    assert_equal(cfg['user.name'], 'myoverride')
    # unset just removes override, not entire config
    cfg.unset('user.name', where='override')
    assert_in('user.name', cfg)
    assert_not_equal('user.name', 'myoverride')
    # add
    # there is no initial increment
    cfg.add('user.name', 'myoverride', where='override')
    assert_equal(cfg['user.name'], 'myoverride')
    # same as with add, not a list
    assert_equal(cfg['user.name'], 'myoverride')
    # but then there is
    cfg.add('user.name', 'myother', where='override')
    assert_equal(cfg['user.name'], ['myoverride', 'myother'])
    # rename
    assert_not_in('ups.name', cfg)
    cfg.rename_section('user', 'ups', where='override')
    # original variable still there
    assert_in('user.name', cfg)
    # rename of override in effect
    assert_equal(cfg['ups.name'], ['myoverride', 'myother'])
    # remove entirely by section
    cfg.remove_section('ups', where='override')
    from datalad.utils import Path
    assert_not_in(
        'ups.name', cfg,
        (cfg._stores,
         cfg.overrides,
    ))


def test_rewrite_url():
    test_cases = (
        # no match
        ('unicorn', 'unicorn'),
        # custom label replacement
        ('example:datalad/datalad.git', 'git@example.com:datalad/datalad.git'),
        # protocol enforcement
        ('git://example.com/some', 'https://example.com/some'),
        # multi-match
        ('mylabel', 'ria+ssh://fully.qualified.com'),
        ('myotherlabel', 'ria+ssh://fully.qualified.com'),
        # conflicts, same label pointing to different URLs
        ('conflict', 'conflict'),
        # also conflicts, but hidden in a multi-value definition
        ('conflict2', 'conflict2'),
    )
    cfg_in = {
        # label rewrite
        'git@example.com:': 'example:',
        # protocol change
        'https://example': 'git://example',
        # multi-value
        'ria+ssh://fully.qualified.com': ('mylabel', 'myotherlabel'),
        # conflicting definitions
        'http://host1': 'conflict',
        'http://host2': 'conflict',
        # hidden conflict
        'http://host3': 'conflict2',
        'http://host4': ('someokish', 'conflict2'),
    }
    cfg = {
        'url.{}.insteadof'.format(k): v
        for k, v in cfg_in.items()
    }
    for input, output in test_cases:
        with swallow_logs(logging.WARNING) as msg:
            assert_equal(rewrite_url(cfg, input), output)
        if input.startswith('conflict'):
            assert_in("Ignoring URL rewrite", msg.out)


# https://github.com/datalad/datalad/issues/4071
@with_tempfile()
@with_tempfile()
def test_no_leaks(path1, path2):
    ds1 = Dataset(path1).create()
    ds1.config.set('i.was.here', 'today', where='local')
    assert_in('i.was.here', ds1.config.keys())
    ds1.config.reload()
    assert_in('i.was.here', ds1.config.keys())
    # now we move into this one repo, and create another
    # make sure that no config from ds1 leaks into ds2
    with chpwd(path1):
        ds2 = Dataset(path2)
        assert_not_in('i.was.here', ds2.config.keys())
        ds2.config.reload()
        assert_not_in('i.was.here', ds2.config.keys())

        ds2.create()
        assert_not_in('i.was.here', ds2.config.keys())

        # and that we do not track the wrong files
        assert_not_in(ds1.pathobj / '.git' / 'config',
                      ds2.config._stores['git']['files'])
        assert_not_in(ds1.pathobj / '.datalad' / 'config',
                      ds2.config._stores['dataset']['files'])
        # these are the right ones
        assert_in(ds2.pathobj / '.git' / 'config',
                  ds2.config._stores['git']['files'])
        assert_in(ds2.pathobj / '.datalad' / 'config',
                  ds2.config._stores['dataset']['files'])


@with_tempfile()
def test_no_local_write_if_no_dataset(path):
    Dataset(path).create()
    with chpwd(path):
        cfg = ConfigManager()
        with assert_raises(CommandError):
            cfg.set('a.b.c', 'd', where='local')


@with_tempfile
def test_dataset_local_mode(path):
    ds = create(path)
    # any sensible (and also our CI) test environment(s) should have this
    assert_in('user.name', ds.config)
    # from .datalad/config
    assert_in('datalad.dataset.id', ds.config)
    # from .git/config
    assert_in('annex.version', ds.config)
    # now check that dataset-local mode doesn't have the global piece
    cfg = ConfigManager(ds, source='dataset-local')
    assert_not_in('user.name', cfg)
    assert_in('datalad.dataset.id', cfg)
    assert_in('annex.version', cfg)


# https://github.com/datalad/datalad/issues/4071
@with_tempfile
def test_dataset_systemglobal_mode(path):
    ds = create(path)
    # any sensible (and also our CI) test environment(s) should have this
    assert_in('user.name', ds.config)
    # from .datalad/config
    assert_in('datalad.dataset.id', ds.config)
    # from .git/config
    assert_in('annex.version', ds.config)
    with chpwd(path):
        # now check that no config from a random dataset at PWD is picked up
        # if not dataset instance was provided
        cfg = ConfigManager(dataset=None, source='any')
        assert_in('user.name', cfg)
        assert_not_in('datalad.dataset.id', cfg)
        assert_not_in('annex.version', cfg)


def test_global_config():

    # from within tests, global config should be read from faked $HOME (see
    # setup_package)
    glb_cfg_file = Path(os.path.expanduser('~')) / '.gitconfig'
    assert any(glb_cfg_file.samefile(Path(p)) for p in dl_cfg._stores['git']['files'])
    assert_equal(dl_cfg.get("user.name"), "DataLad Tester")
    assert_equal(dl_cfg.get("user.email"), "test@example.com")


@with_tempfile()
def test_bare(path):
    # can we handle a bare repo?
    gr = GitRepo(path, create=True, bare=True)
    # do we read the correct local config?
    assert_in(gr.pathobj / 'config', gr.config._stores['git']['files'])
    # any sensible (and also our CI) test environment(s) should have this
    assert_in('user.name', gr.config)
    # not set something that wasn't there
    obscure_key = 'sec.reallyobscurename!@@.key'
    assert_not_in(obscure_key, gr.config)
    # to the local config, which is easily accessible
    gr.config.set(obscure_key, 'myvalue', where='local')
    assert_equal(gr.config.get(obscure_key), 'myvalue')
    # now make sure the config is where we think it is
    assert_in(obscure_key.split('.')[1], (gr.pathobj / 'config').read_text())


@with_tempfile()
def test_write_config_section(path):
    # can we handle a bare repo?
    gr = GitRepo(path, create=True, bare=True)

    # test cases
    # first 3 args are write_config_section() parameters
    # 4th arg is a list with key/value pairs that should end up in a
    # ConfigManager after a reload
    testcfg = [
        ('submodule', 'sub', dict(active='true', url='http://example.com'), [
            ('submodule.sub.active', 'true'),
            ('submodule.sub.url', 'http://example.com'),
        ]),
        ('submodule', 'sub"quote', {"a-b": '"quoted"', 'c': 'with"quote'}, [
            ('submodule.sub"quote.a-b', '"quoted"'),
            ('submodule.sub"quote.c', 'with"quote'),
        ]),
        ('short', ' s p a c e ', {"a123": ' space all over '}, [
            ('short. s p a c e .a123', ' space all over '),
        ]),
    ]

    for tc in testcfg:
        # using append mode to provoke potential interference by
        # successive calls
        with (gr.pathobj / 'config').open('a') as fobj:
            write_config_section(fobj, tc[0], tc[1], tc[2])
        gr.config.reload()
        for testcase in tc[3]:
            assert_in(testcase[0], gr.config)
            assert_equal(testcase[1], gr.config[testcase[0]])


@with_tempfile()
def test_external_modification(path):
    from datalad.cmd import WitlessRunner as Runner
    runner = Runner(cwd=path)
    repo = GitRepo(path, create=True)
    config = repo.config

    key = 'sec.sub.key'
    assert_not_in(key, config)
    config.set(key, '1', where='local')
    assert_equal(config[key], '1')

    # we pick up the case where we modified so size changed
    runner.run(['git', 'config', '--local', '--replace-all', key, '10'])
    # unfortunately we do not react for .get unless reload. But here
    # we will test if reload is correctly decides to reload without force
    config.reload()
    assert_equal(config[key], '10')

    # and no size change
    runner.run(['git', 'config', '--local', '--replace-all', key, '11'])
    config.reload()
    assert_equal(config[key], '11')
