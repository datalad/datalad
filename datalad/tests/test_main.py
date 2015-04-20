#emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
#ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os, tempfile, time, platform
from os.path import join, exists, lexists, isdir

from .utils import eq_, ok_, assert_greater, \
     with_tree, serve_path_via_http, sorted_files, rmtree, create_archive, \
     md5sum, ok_clean_git, ok_file_under_git, get_most_obscure_supported_name, \
     on_windows, on_osx
from nose.exc import SkipTest

from ..config import EnhancedConfigParser
from ..crawler.main import DoubleAnnexRepo
from ..db import load_db

# Too many things at a time. For now skip crawler tests on windows:
if on_windows:
    raise SkipTest

tree1args = dict(
    tree=(
        ('test.txt', 'abracadabra'),
        ('test.ascii', 'abracadabra'),
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), ))),
    dir=os.curdir,
    prefix='.tmp-page2annex-')

def verify_files_content(d, files, dangling=[]):
    for f in files:
        f_ = join(d, f)
        ok_(lexists(f_), f_)      # if a link exists at all
        if f in dangling:
            ok_(not exists(f_), f_)       # and if it is not dangling
        else:
            ok_(exists(f_), f_)       # and if it is not dangling
            if f_.endswith('/test.txt'):
                eq_(open(f_).read(), 'abracadabra', f_)
            if f_.endswith('/d'):
                ok_(isdir(f_), f_)
            if f == '.page2annex':
                # verify all it loads ok
                ok_(load_db(f_))

# TODO: move check ok_file_under_git here
def verify_files(d,
                 annex,
                 git=[],
                 dangling=[], untracked=[]):
    ok_clean_git(d, untracked=untracked)
    files = sorted_files(d)
    target_files_all = set(annex + git + dangling + untracked)
    eq_(set(files), target_files_all, "%s: %s != %s" % (d, files, target_files_all))
    verify_files_content(d, annex + git, dangling=dangling)
    for f in git:
        ok_file_under_git(d, f)


def verify_nothing_was_done(stats):
    eq_(stats['downloads'], 0)
    eq_(stats['incoming_annex_updates'], 0)
    eq_(stats['public_annex_updates'], 0)
    eq_(stats['downloaded'], 0)

@with_tree(**tree1args)
@serve_path_via_http()
def check_page2annex_same_incoming_and_public(mode, path, url):
    dout = tempfile.mkdtemp()
    cfg = EnhancedConfigParser.get_default(dict(
        DEFAULT=dict(
            incoming=dout,
            public=dout,
            description="test",
            mode=mode,
            ),
        files=dict(
            directory='files',  # TODO: recall what was wrong with __name__ substitution, look into fail2ban/client/configparserinc.py
            url=url,
            git_add='(\.ascii)')))

    drepo = DoubleAnnexRepo(cfg)
    stats1_dry = drepo.page2annex(dry_run=True)
    verify_nothing_was_done(stats1_dry)

    stats1 = drepo.page2annex()
    # they both should match
    eq_(stats1['incoming_annex_updates'], 3)
    eq_(stats1['public_annex_updates'], 3)
    # in fast/relaxed mode we still need to fetch 1 archive, 1 for .ascii
    eq_(stats1['downloads'], 1 + int(mode=='download') + 1)
    eq_(stats1['sections'], 1)
    assert_greater(stats1['downloaded'], 100)   # should be more than 100b
    # verify that .ascii file was added directly to GIT
    ok_file_under_git(dout, os.path.join('files', 'test.txt'), annexed=True)
    ok_file_under_git(dout, os.path.join('files', 'test.ascii'), annexed=False)

    ok_clean_git(dout)

    # Let's repeat -- there should be no downloads/updates
    stats2 = drepo.page2annex()
    verify_nothing_was_done(stats2)
    ok_clean_git(dout)

    ok_(exists(join(dout, '.git')))
    ok_(exists(join(dout, '.git', 'annex')))

    eq_(sorted_files(dout),
        ['.page2annex',
         # there should be no 1/1
         'files/1/1 f.txt',
         'files/1/d/1d',
         'files/test.ascii',
         'files/test.txt',
        ])

    stats2_dry = drepo.page2annex(dry_run=True)
    verify_nothing_was_done(stats2_dry)
    ok_clean_git(dout)

    rmtree(dout, True)

def test_page2annex_same_incoming_and_public():
    for mode in ('download',
                 'fast',
                 'relaxed'
                 ):
        yield check_page2annex_same_incoming_and_public, mode



@with_tree(**tree1args)
@serve_path_via_http()
def check_page2annex_separate_public(separate, mode, incoming_destiny, path, url):
    fast_mode = mode in ['fast', 'relaxed']
    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp() if separate else din

    cfg = EnhancedConfigParser.get_default(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test", mode=mode),
        files=dict(directory='files', incoming_destiny=incoming_destiny, url=url, git_add='\.ascii')))

    drepo = DoubleAnnexRepo(cfg)
    stats1_dry = drepo.page2annex(dry_run=True)
    verify_nothing_was_done(stats1_dry)
    ok_(not exists(join(din, '.git')))
    ok_(not exists(join(dout, '.git')))

    stats1 = drepo.page2annex()
    # dangling is just for broken/hanging symlinks
    dangling = ['files/test.txt'] if mode != 'download' else []
    verify_files(dout,
        annex=['files/1/1 f.txt', 'files/1/d/1d', 'files/test.txt'],
        git=['files/test.ascii'],
        dangling=dangling)
    eq_(stats1['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] else 3)
    eq_(stats1['public_annex_updates'], 3)
    # in fast/relaxed mode we still need to fetch 1 archive, 1 for .ascii
    eq_(stats1['downloads'], 1 + int(mode=='download') + 1)
    eq_(stats1['sections'], 1)
    assert_greater(stats1['downloaded'], 100)   # should be more than 100b

    # Let's add a bogus local file in din and track that it would not
    # get committed
    with open(join(din, 'files', 'BOGUS.txt'), 'w') as f:
        f.write("BOGUS")
    # So which files should be present but not be committed
    din_untracked = ['files/BOGUS.txt']
    if incoming_destiny == 'keep':
        din_untracked += ['files/1.tar.gz', 'files/test.ascii']
        if mode == 'download':
            # we download it but do not commit
            din_untracked += ['files/test.txt']

    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)
    # Let's repeat -- there should be no downloads/updates of any kind
    # since we had no original failures nor added anything
    stats2 = drepo.page2annex()
    verify_nothing_was_done(stats2)
    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)

    ok_(exists(join(din, '.git')))
    # TODO: actually this one should not be there if 'keep'
    # and only .git to track our .page2annex
    ok_(exists(join(din, '.git', 'annex')))

    # Test the "incoming" appearance
    if incoming_destiny == 'annex':
        verify_files(din,
            ['.page2annex', 'files/1.tar.gz', 'files/test.txt'],
            git=['files/test.ascii'],
            dangling=dangling, untracked=din_untracked)
    elif incoming_destiny == 'keep':
        # if mode is fast they will not be even downloaded to incoming,
        # unless an archive
        verify_files(din,
            ['.page2annex', 'files/1.tar.gz'],
            # nothing to dangle -- we keep
            #dangling=dangling,
            untracked=din_untracked)
    elif incoming_destiny == 'drop':
        verify_files(din,
            ['.page2annex', 'files/1.tar.gz', 'files/test.txt'],
            git=['files/test.ascii'],
            dangling=dangling + ['files/1.tar.gz', 'files/test.txt'],
            untracked=din_untracked)
    else:                           # 'rm'
        eq_(incoming_destiny, 'rm')
        # incoming files will not be there at all
        verify_files(din, ['.page2annex'],
                     # nothing to dangle -- they are removed
                     # dangling=dangling,
                     untracked=din_untracked)

    # Test the "public" appearance
    ok_(exists(join(dout, '.git', 'annex')))
    verify_files(dout,
        ['files/1/1 f.txt', 'files/1/d/1d', 'files/test.txt'],
        git=['files/test.ascii'],
        dangling=dangling)

    stats2_dry = drepo.page2annex(dry_run=True)
    verify_nothing_was_done(stats2_dry)

    # now check for the updates in a file
    # appending
    # Twice 'w' so we do change the file although keeping the size
    # (and even content) the same (but sleep for a second for
    # freshier mtime). and last 'w' so change the size but unlikely mtime
    for i, (m, load) in enumerate((('a', 'a'),
                                   ('w', 'w'),
                                   ('w', 'w'),
                                   ('w', 'ww'))):
        with open(join(path, 'test.txt'), m) as f:
            f.write(load)
        stats = drepo.page2annex()
        ok_clean_git(din, untracked=din_untracked)
        ok_clean_git(dout)
        eq_(stats['incoming_annex_updates'],
            0 if incoming_destiny in ['rm', 'keep'] or mode == 'relaxed' else 1)
        eq_(stats['public_annex_updates'], 1 if mode != 'relaxed' else 0)
        eq_(stats['downloads'], int(mode=='download'))
        # Load the file from incoming
        target_load = 'abracadabra%s' % load if m=='a' else load
        if incoming_destiny in ['annex', 'keep'] and mode == 'download':
            with open(join(din, 'files', 'test.txt')) as f:
                eq_(f.read(), target_load)
        # Load the file from public
        if mode == 'download':
            with open(join(dout, 'files', 'test.txt')) as f:
                eq_(f.read(), target_load)
        else:
            # it must be a hanging symlink
            ok_(lexists(join(dout, 'files', 'test.txt')))
            ok_(not exists(join(dout, 'files', 'test.txt')))

        stats_dry = drepo.page2annex(dry_run=True)
        verify_nothing_was_done(stats_dry)
        if i == 1:
            # we need to sleep at least for a second so that
            # time-stamp of URL changes
            assert(m=='w')
            time.sleep(1)

    # And now check updates in the archive
    old_md5sum = md5sum(join(path, '1.tar.gz'))

    # Archive gets replaced with identical but freshly generated one:
    # there should be no crashed or complaints and updates should
    # still happen as far as the action is concerned
    create_archive(path, '1.tar.gz',
            (('1 f.txt', '1 f load'),
             ('d', (('1d', ''),)),))
    stats = drepo.page2annex()
    eq_(stats['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] or mode == 'relaxed' else 1)
    eq_(stats['public_annex_updates'], 1 if mode != 'relaxed' else 0)
    eq_(stats['downloads'], 1 if mode != 'relaxed' else 0)
    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)

    # Archive gets content in one of the files modified
    target_load = '1 f load updated'
    create_archive(path, '1.tar.gz',
            (('1 f.txt', '1 f load updated'),
             ('d', (('1d', ''),)),))
    stats = drepo.page2annex()
    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)
    eq_(stats['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] or mode == 'relaxed' else 1)
    full_incoming_name = join(din, 'files', '1.tar.gz')
    if incoming_destiny in ['annex', 'keep']:
        if mode != 'relaxed':
            # it must be the same as the incoming archive
            eq_(md5sum(join(path, '1.tar.gz')),
                md5sum(full_incoming_name))
        else:
            # we should have retained the old md5sum
            eq_(old_md5sum,
                md5sum(full_incoming_name))

    else:
        # it must be gone
        ok_(not exists(full_incoming_name))
    eq_(stats['public_annex_updates'], 1 if mode != 'relaxed' else 0)
    eq_(stats['downloads'], 1 if mode != 'relaxed' else 0)            # needs to be downloaded!
    # and now because file comes from an archive it must always be
    # there
    with open(join(dout, 'files', '1', '1 f.txt')) as f:
        if mode != 'relaxed':
            eq_(f.read(), target_load)

    # TODO: directory within archive gets renamed
    # yet to clarify how we treat those beasts

    # TODO: "removal" mode, when files get removed"

    rmtree(dout, True)
    rmtree(din, True)

def test_page2annex_separate_public():
    # separate lines for easy selection for debugging of a particular
    # test
    for separate in (#False,
                     True,
                     ):
        for mode in ('download',
                     'fast',
                     'relaxed',
                     ):
            for incoming_destiny in ('annex',
                                     'drop',
                                     'rm',
                                     'keep',
                                     ):
                yield check_page2annex_separate_public, separate, mode, incoming_destiny

obscure = get_most_obscure_supported_name()

if on_osx:
    # There is a known issue with annex under OSX
    # https://github.com/datalad/datalad/issues/79
    import logging
    lgr = logging.getLogger('datalad.tests')
    lgr.warn("TODO: placing non-empty load until #79 is fixed")
    empty_load = "LOAD"
else:
    empty_load = ''

# now with some recursive structure of directories
tree2args = dict(
    tree=(
        ('test.txt', 'abracadabra'),
        (obscure, empty_load),
        ('2', (
            # this is yet to troubleshoot
            #(u'юнякод.txt', u'и тут юнякод'),
            ('d', (('1d', empty_load),)),
            ('f', (('1d', empty_load),)),
            )),
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), ))),
    dir=os.curdir,
    prefix='.tmp-page2annex-')

@with_tree(**tree2args)
@serve_path_via_http()
def test_page2annex_recurse(path, url):

    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp()

    cfg = EnhancedConfigParser.get_default(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test", recurse='/$'),
        files=dict(directory='', incoming_destiny='annex', url=url)))

    drepo = DoubleAnnexRepo(cfg)
    stats1 = drepo.page2annex()

    verify_files(din,
        [obscure, '.page2annex', '1.tar.gz', #u'2/юнякод.txt',
                                    '2/d/1d', '2/f/1d', 'test.txt'])
    verify_files(dout,
        [obscure, '1/1 f.txt', '1/d/1d',     #u'2/юнякод.txt',
                                    '2/d/1d', '2/f/1d', 'test.txt'])

    #rmtree(dout, True)
    #rmtree(din, True)
