#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
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
from os.path import join, exists

from .utils import eq_, ok_, assert_greater, \
     with_tree, serve_path_via_http, sorted_files, rmtree

from ..config import get_default_config
from ..main import rock_and_roll

tree1args = dict(
    tree=(
        ('test.txt', 'abracadabra'),
        ('1.tar.gz', (
            ('1f.txt', '1f load'),
            ('d', (('1d', ''),)), ))),
    dir=os.curdir,
    prefix='.tmp-page2annex-')

@with_tree(**tree1args)
@serve_path_via_http()
def test_rock_and_roll_same_incoming_and_public(url):
    dout = tempfile.mkdtemp()

    cfg = get_default_config(dict(
        DEFAULT=dict(
            incoming=dout,
            public=dout,
            description="test",
            ),
        files=dict(
            directory='files', # TODO: recall what was wrong with __name__ substitution, look into fail2ban/client/configparserinc.py
            url=url)))

    stats1 = rock_and_roll(cfg, dry_run=False)
    eq_(stats1['annex_updates'], 2)
    eq_(stats1['downloads'], 2)
    eq_(stats1['sections'], 1)
    assert_greater(stats1['size'], 100)   # should be more than 100b

    # Let's repeat -- there should be no downloads/updates
    stats2 = rock_and_roll(cfg, dry_run=False)
    eq_(stats2['downloads'], 0)
    eq_(stats2['annex_updates'], 0)
    eq_(stats2['size'], 0)

    ok_(exists(join(dout, '.git')))
    ok_(exists(join(dout, '.git', 'annex')))

    eq_(sorted_files(dout),
        ['.page2annex',
         # there should be no 1/1
         'files/1/1f.txt',
         'files/1/d/1d',
         'files/test.txt',
        ])
    rmtree(dout, True)



@with_tree(**tree1args)
@serve_path_via_http()
def test_rock_and_roll_separate_public(url):
    din = tempfile.mkdtemp()
    dout = tempfile.mkdtemp()

    cfg = get_default_config(dict(
        DEFAULT=dict(incoming=din, public=dout, description="test"),
        files=dict(directory='files', archives_destiny='annex', url=url)))

    stats1 = rock_and_roll(cfg, dry_run=False)
    eq_(stats1['annex_updates'], 2)
    eq_(stats1['downloads'], 2)
    eq_(stats1['sections'], 1)
    assert_greater(stats1['size'], 100)   # should be more than 100b

    # Let's repeat -- there should be no downloads/updates
    stats2 = rock_and_roll(cfg, dry_run=False)
    eq_(stats2['downloads'], 0)
    eq_(stats2['annex_updates'], 0)
    eq_(stats2['size'], 0)

    ok_(exists(join(din, '.git')))
    ok_(exists(join(din, '.git', 'annex')))
    eq_(sorted_files(din),
        ['.page2annex', 'files/1.tar.gz', 'files/test.txt'])

    ok_(exists(join(dout, '.git')))
    ok_(exists(join(dout, '.git', 'annex')))
    eq_(sorted_files(dout),
        ['files/1/1f.txt', 'files/1/d/1d', 'files/test.txt'])

    rmtree(dout, True)
    rmtree(din, True)
