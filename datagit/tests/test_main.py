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

import os, tempfile
from os.path import join, exists, lexists, isdir

from .utils import eq_, ok_, assert_greater, \
     with_tree, serve_path_via_http, sorted_files, rmtree

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

def verify_files_content(d, files, broken=[]):
    for f in files:
        f_ = join(d, f)
        ok_(lexists(f_), f_)      # if a link exists at all
        if f in broken:
            ok_(not exists(f_), f_)       # and if it is not broken
        else:
            ok_(exists(f_), f_)       # and if it is not broken
            if f_.endswith('/test.txt'):
                eq_(open(f_).read(), 'abracadabra', f_)
            if f_.endswith('/d'):
                ok_(isdir(f_), f_)
            if f == '.page2annex':
                # verify all it loads ok
                ok_(load_db(f_))

def verify_files(d, target_files, broken=[]):
    files = sorted_files(d)
    eq_(files, target_files, "%s: %s != %s" % (d, files, target_files))
    verify_files_content(d, target_files, broken=broken)

def verify_nothing_was_done(stats):
    eq_(stats['downloads'], 0)
    eq_(stats['incoming_annex_updates'], 0)
    eq_(stats['public_annex_updates'], 0)
    eq_(stats['downloaded'], 0)

@with_tree(**tree1args)
@serve_path_via_http()
def check_rock_and_roll_same_incoming_and_public(url, mode):
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

    # Let's repeat -- there should be no downloads/updates
    stats2 = rock_and_roll(cfg, dry_run=False)
    verify_nothing_was_done(stats2)

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

    rmtree(dout, True)

def test_rock_and_roll_same_incoming_and_public():
    for mode in ('download',
                 'fast',
                 'relaxed'
                 ):
        yield check_rock_and_roll_same_incoming_and_public, mode



@with_tree(**tree1args)
@serve_path_via_http()
def check_rock_and_roll_separate_public(url, mode, incoming_destiny):
    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp()

    cfg = get_default_config(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test", mode=mode),
        files=dict(directory='files', incoming_destiny=incoming_destiny, url=url)))

#    import pydb; pydb.debugger()
    stats1_dry = rock_and_roll(cfg, dry_run=True)
    verify_nothing_was_done(stats1_dry)

    stats1 = rock_and_roll(cfg, dry_run=False)
    broken = ['files/test.txt'] if mode != 'download' else []
    verify_files(dout,
        ['files/1/1 f.txt', 'files/1/d/1d', 'files/test.txt'],
        broken=broken)
    eq_(stats1['incoming_annex_updates'], 2 if incoming_destiny != 'rm' else 0)
    eq_(stats1['public_annex_updates'], 2)
    # in fast/relaxed mode we still need to fetch 1 archive
    eq_(stats1['downloads'], 1 + int(mode=='download'))
    eq_(stats1['sections'], 1)
    assert_greater(stats1['downloaded'], 100)   # should be more than 100b

    # Let's repeat -- there should be no downloads/updates of any kind
    # since we had no original failures nor added anything
    stats2 = rock_and_roll(cfg, dry_run=False)
    verify_nothing_was_done(stats2)

    ok_(exists(join(din, '.git')))
    ok_(exists(join(din, '.git', 'annex')))

    if incoming_destiny == 'annex':
        verify_files(din,
            ['.page2annex', 'files/1.tar.gz', 'files/test.txt'],
            broken=broken)
    elif incoming_destiny == 'drop':
        verify_files(din,
            ['.page2annex', 'files/1.tar.gz', 'files/test.txt'],
            broken=broken + ['files/1.tar.gz', 'files/test.txt'])
    else:                           # 'rm'
        eq_(incoming_destiny, 'rm')
        # incoming files will not be there at all
        verify_files(din, ['.page2annex'], broken=broken)

    ok_(exists(join(dout, '.git')))
    ok_(exists(join(dout, '.git', 'annex')))
    verify_files(dout,
        ['files/1/1 f.txt', 'files/1/d/1d', 'files/test.txt'],
        broken=broken)

    stats2_dry = rock_and_roll(cfg, dry_run=True)
    verify_nothing_was_done(stats2_dry)

    rmtree(dout, True)
    rmtree(din, True)

def test_rock_and_roll_separate_public():
    for mode in ('download',
                 'fast',
                 'relaxed'
                 ):
        for incoming_destiny in ('annex', 'drop', 'rm'):
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
def test_rock_and_roll_recurse(url):

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
