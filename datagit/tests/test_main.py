#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import os, tempfile, time
from os.path import join, exists, lexists, isdir

from .utils import eq_, ok_, assert_greater, \
     with_tree, serve_path_via_http, sorted_files, rmtree, create_archive, \
     md5sum, ok_clean_git

from ..config import get_default_config
from ..main import rock_and_roll
from ..db import load_db


tree1args = dict(
    tree=(
        ('test.txt', 'abracadabra'),
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

def verify_files(d, target_files, dangling=[], untracked=[]):
    ok_clean_git(d, untracked=untracked)
    files = sorted_files(d)
    target_files_all = set(target_files + dangling + untracked)
    eq_(set(files), target_files_all, "%s: %s != %s" % (d, files, target_files_all))
    verify_files_content(d, target_files, dangling=dangling)

def verify_nothing_was_done(stats):
    eq_(stats['downloads'], 0)
    eq_(stats['incoming_annex_updates'], 0)
    eq_(stats['public_annex_updates'], 0)
    eq_(stats['downloaded'], 0)

@with_tree(**tree1args)
@serve_path_via_http()
def check_rock_and_roll_same_incoming_and_public(url, mode, path):
    dout = tempfile.mkdtemp()
    cfg = get_default_config(dict(
        DEFAULT=dict(
            incoming=dout,
            public=dout,
            description="test",
            mode=mode,
            ),
        files=dict(
            directory='files', # TODO: recall what was wrong with __name__ substitution, look into fail2ban/client/configparserinc.py
            url=url)))

    stats1_dry = rock_and_roll(cfg, dry_run=True)
    verify_nothing_was_done(stats1_dry)

    stats1 = rock_and_roll(cfg, dry_run=False)
    # they both should match
    eq_(stats1['incoming_annex_updates'], 2)
    eq_(stats1['public_annex_updates'], 2)
    # in fast/relaxed mode we still need to fetch 1 archive
    eq_(stats1['downloads'], 1 + int(mode=='download'))
    eq_(stats1['sections'], 1)
    assert_greater(stats1['downloaded'], 100)   # should be more than 100b
    ok_clean_git(dout)

    # Let's repeat -- there should be no downloads/updates
    stats2 = rock_and_roll(cfg, dry_run=False)
    verify_nothing_was_done(stats2)
    ok_clean_git(dout)

    ok_(exists(join(dout, '.git')))
    ok_(exists(join(dout, '.git', 'annex')))

    eq_(sorted_files(dout),
        ['.page2annex',
         # there should be no 1/1
         'files/1/1 f.txt',
         'files/1/d/1d',
         'files/test.txt',
        ])

    stats2_dry = rock_and_roll(cfg, dry_run=True)
    verify_nothing_was_done(stats2_dry)
    ok_clean_git(dout)

    rmtree(dout, True)

def test_rock_and_roll_same_incoming_and_public():
    for mode in ('download',
                 'fast',
                 'relaxed'
                 ):
        yield check_rock_and_roll_same_incoming_and_public, mode



@with_tree(**tree1args)
@serve_path_via_http()
def check_rock_and_roll_separate_public(url, mode, incoming_destiny, path):
    fast_mode = mode in ['fast', 'relaxed']
    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp()

    cfg = get_default_config(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test", mode=mode),
        files=dict(directory='files', incoming_destiny=incoming_destiny, url=url)))

    stats1_dry = rock_and_roll(cfg, dry_run=True)
    verify_nothing_was_done(stats1_dry)
    ok_(not exists(join(din, '.git')))
    ok_(not exists(join(dout, '.git')))

    stats1 = rock_and_roll(cfg, dry_run=False)
    # dangling is just for broken/hanging symlinks
    dangling = ['files/test.txt'] if mode != 'download' else []
    verify_files(dout,
        ['files/1/1 f.txt', 'files/1/d/1d', 'files/test.txt'],
        dangling=dangling)
    eq_(stats1['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] else 2)
    eq_(stats1['public_annex_updates'], 2)
    # in fast/relaxed mode we still need to fetch 1 archive
    eq_(stats1['downloads'], 1 + int(mode=='download'))
    eq_(stats1['sections'], 1)
    assert_greater(stats1['downloaded'], 100)   # should be more than 100b

    # Let's add a bogus local file in din and track that it would not
    # get committed
    with open(join(din, 'files', 'BOGUS.txt'), 'w') as f:
        f.write("BOGUS")
    # So which files should be present but not be committed
    din_untracked = ['files/BOGUS.txt']
    if incoming_destiny == 'keep':
        din_untracked += ['files/1.tar.gz']
        if mode == 'download':
            # we download it but do not commit
            din_untracked += ['files/test.txt']

    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)

    # Let's repeat -- there should be no downloads/updates of any kind
    # since we had no original failures nor added anything
    stats2 = rock_and_roll(cfg, dry_run=False)
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
        dangling=dangling)

    stats2_dry = rock_and_roll(cfg, dry_run=True)
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
        stats = rock_and_roll(cfg, dry_run=False)
        ok_clean_git(din, untracked=din_untracked)
        ok_clean_git(dout)
        eq_(stats['incoming_annex_updates'],
            0 if incoming_destiny in ['rm', 'keep'] else 1)
        eq_(stats['public_annex_updates'], 1)
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

        stats_dry = rock_and_roll(cfg, dry_run=True)
        verify_nothing_was_done(stats_dry)
        if i == 1:
            # we need to sleep at least for a second so that
            # time-stamp of URL changes
            assert(m=='w')
            time.sleep(1)

    # And now check updates in the archive

    # Archive gets replaced with identical but freshly generated one:
    # there should be no crashed or complaints and updates should
    # still happen as far as the action is concerned
    create_archive(path, '1.tar.gz',
            (('1 f.txt', '1 f load'),
             ('d', (('1d', ''),)),))
    stats = rock_and_roll(cfg, dry_run=False)
    eq_(stats['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] else 1)
    eq_(stats['public_annex_updates'], 1)
    eq_(stats['downloads'], 1)
    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)

    # Archive gets content in one of the files modified
    target_load = '1 f load updated'
    create_archive(path, '1.tar.gz',
            (('1 f.txt', '1 f load updated'),
             ('d', (('1d', ''),)),))
    stats = rock_and_roll(cfg, dry_run=False)
    ok_clean_git(din, untracked=din_untracked)
    ok_clean_git(dout)
    eq_(stats['incoming_annex_updates'],
        0 if incoming_destiny in ['rm', 'keep'] else 1)
    full_incoming_name = join(din, 'files', '1.tar.gz')
    if incoming_destiny in ['annex', 'keep']:
        # it must be the same as the incoming archive
        eq_(md5sum(join(path, '1.tar.gz')),
            md5sum(full_incoming_name))
    else:
        # it must be gone
        ok_(not exists(full_incoming_name))
    eq_(stats['public_annex_updates'], 1)
    eq_(stats['downloads'], 1)            # needs to be downloaded!
    # and now because file comes from an archive it must always be
    # there
    with open(join(dout, 'files', '1', '1 f.txt')) as f:
        eq_(f.read(), target_load)

    # TODO: directory within archive gets renamed
    # yet to clarify how we treat those beasts

    # TODO: "removal" mode, when files get removed"

    rmtree(dout, True)
    rmtree(din, True)

def test_rock_and_roll_separate_public():
    # separate lines for easy selection for debugging of a particular
    # test
    for mode in ('download',
                 'fast',
                 'relaxed',
                 ):
        for incoming_destiny in ('annex',
                                 'drop',
                                 'rm',
                                 'keep',
                                 ):
            yield check_rock_and_roll_separate_public, mode, incoming_destiny


# now with some recursive structure of directories
tree2args = dict(
    tree=(
        ('test.txt', 'abracadabra'),
        ("\"';a&b&cd|", ""),
        ('2', (
            # this is yet to troubleshoot
            #(u'юнякод.txt', u'и тут юнякод'),
            ('d', (('1d', ''),)),
            ('f', (('1d', ''),)),
            )),
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), ))),
    dir=os.curdir,
    prefix='.tmp-page2annex-')

@with_tree(**tree2args)
@serve_path_via_http()
def test_rock_and_roll_recurse(url, path):

    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp()

    cfg = get_default_config(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test", recurse='/$'),
        files=dict(directory='', incoming_destiny='annex', url=url)))

    stats1 = rock_and_roll(cfg, dry_run=False)

    verify_files(din,
        ["\"';a&b&cd|", '.page2annex', '1.tar.gz', #u'2/юнякод.txt',
                                    '2/d/1d', '2/f/1d', 'test.txt'])
    verify_files(dout,
        ["\"';a&b&cd|", '1/1 f.txt', '1/d/1d',     #u'2/юнякод.txt',
                                    '2/d/1d', '2/f/1d', 'test.txt'])

    #rmtree(dout, True)
    #rmtree(din, True)
