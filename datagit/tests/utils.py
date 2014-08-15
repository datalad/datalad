#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:
"""
 DESCRIPTION (NOTES):

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

import shutil, stat, os, sys

from ..cmd import Runner
from ..repos import AnnexRepo

from nose.tools import assert_equal, assert_raises, assert_greater, raises, \
    make_decorator, ok_, eq_
import tempfile

from nose.tools import make_decorator

def rmtree(path, *args, **kwargs):
    """To remove git-annex .git it is needed to make all files and directories writable again first
    """
    for root, dirs, files in os.walk(path):
        for f in files:
            fullf = os.path.join(root, f)
            # might be the "broken" symlink which would fail to stat etc
            if os.path.exists(fullf):
                os.chmod(fullf, os.stat(fullf).st_mode | stat.S_IWRITE | stat.S_IREAD)
        os.chmod(root, os.stat(root).st_mode | stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(path, *args, **kwargs)

def create_archive(path, name, load):
    dirname = name[:-7]
    full_dirname = os.path.join(path, dirname)
    os.makedirs(full_dirname)
    create_tree(full_dirname, load)
    # create archive
    status, output = Runner().getstatusoutput(
        'cd %(path)s && tar -czvf %(name)s %(dirname)s' % locals())
    # remove original tree
    shutil.rmtree(full_dirname)

def create_tree(path, tree):
    """Given a list of tuples (name, load) create such a tree

    if load is a tuple itself -- that would create either a subtree or an archive
    with that content and place it into the tree if name ends with .tar.gz
    """
    if not os.path.exists(path):
        os.makedirs(path)

    for name, load in tree:
        full_name = os.path.join(path, name)
        if isinstance(load, tuple):
            if name.endswith('.tar.gz'):
                create_archive(path, name, load)
            else:
                create_tree(full_name, load)
        else:
            #encoding = sys.getfilesystemencoding()
            #if isinstance(full_name, unicode):
            #    import pydb; pydb.debugger()
            with open(full_name, 'w') as f:
                if isinstance(load, unicode):
                    load = load.encode('utf-8')
                f.write(load)

def with_tree(tree=None, **tkwargs):
    def decorate(func):
        def newfunc(*arg, **kw):
            d = tempfile.mkdtemp(**tkwargs)
            create_tree(d, tree)
            try:
                func(*((d,) + arg), **kw)
            finally:
                #print "TODO: REMOVE tree ", d
                shutil.rmtree(d)
        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate


import md5
def md5sum(filename):
    with open(filename) as f:
        return md5.md5(f.read()).hexdigest()


import git
from os.path import exists, join
def ok_clean_git(path, annex=True, untracked=[]):
    """Verify that under given path there is a clean git repository

    it exists, .git exists, nothing is uncommitted/dirty/staged
    """
    ok_(exists(path))
    ok_(exists(join(path, '.git')))
    if annex:
        ok_(exists(join(path, '.git', 'annex')))
    repo = git.Repo(path)

    ok_(repo.head.is_valid())

    # get string representations of diffs with index to ease troubleshooting
    index_diffs = [str(d) for d in repo.index.diff(None)]
    head_diffs = [str(d) for d in repo.index.diff(repo.head.commit)]

    eq_(sorted(repo.untracked_files), sorted(untracked))
    eq_(index_diffs, [])
    eq_(head_diffs, [])

def ok_file_under_git(path, filename, annexed=False):
    repo = AnnexRepo(path)
    assert(filename in repo.get_indexed_files()) # file is known to Git
    assert(annexed == os.path.islink(os.path.join(path, filename)))


# GRRR -- this one is crippled since path where HTTPServer is serving
# from can't be changed without pain.
import logging
import random
import SimpleHTTPServer
import SocketServer
from threading import Thread

lgr = logging.getLogger('datagit')

class SilentHTTPHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """A little adapter to silence the handler
    """
    def __init__(self, *args, **kwargs):
        self._silent = lgr.getEffectiveLevel() > logging.DEBUG
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, format, *args):
        if self._silent:
            return
        lgr.debug("HTTP: " + format % args)

def serve_path_via_http(*args, **tkwargs):
    def decorate(func):
        def newfunc(path, *arg, **kw):
            port = random.randint(8000, 8500)
            #print "Starting to serve path ", path
            # TODO: ATM we are relying on path being local so we could
            # start HTTP server in the same directory.  FIX IT!
            SocketServer.TCPServer.allow_reuse_address = True
            httpd = SocketServer.TCPServer(("", port), SilentHTTPHandler)
            server_thread = Thread(target=httpd.serve_forever)
            url = 'http://localhost:%d/%s/' % (port, path)
            lgr.debug("HTTP: serving %s under %s", path, url)
            server_thread.start()
            if 'path' in kw:
                raise ValueError(
                    "path kwarg to be provided by serve_path_via_http")
            kw_ = {'path': path}
            kw_.update(kw)

            #time.sleep(1)               # just give it few ticks
            try:
                func(*((url,)+arg), **kw_)
            finally:
                lgr.debug("HTTP: stopping server")
                httpd.shutdown()
                #print "Waiting for thread to stop"
                server_thread.join()
        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate

def sorted_files(dout):
    """Return a (sorted) list of files under dout
    """
    return sorted(sum([[os.path.join(r, f)[len(dout)+1:] for f in files]
                       for r,d,files in os.walk(dout)
                       if not '.git' in r], []))

import glob
def with_tempfile(*targs, **tkwargs):
    """Decorator function to provide a temporary file name and remove it at the end.

    All arguments are passed into the call to tempfile.mktemp(), and
    resultant temporary filename is passed as the first argument into
    the test.  If no 'prefix' argument is provided, it will be
    constructed using module and function names ('.' replaced with
    '_').

    Example use::

        @with_tempfile()
        def test_write(tfile):
            open(tfile, 'w').write('silly test')
    """

    def decorate(func):
        def newfunc(*arg, **kw):
            if len(targs)<2 and not 'prefix' in tkwargs:
                try:
                    tkwargs['prefix'] = 'tempfile_%s.%s' \
                                        % (func.__module__, func.func_name)
                except:
                    # well -- if something wrong just proceed with defaults
                    pass

            filename = tempfile.mktemp(*targs, **tkwargs)
            if __debug__:
                lgr.debug('Running %s with temporary filename %s'
                          % (func.__name__, filename))
            try:
                func(*(arg + (filename,)), **kw)
            finally:
                # glob here for all files with the same name (-suffix)
                # would be useful whenever we requested .img filename,
                # and function creates .hdr as well
                lsuffix = len(tkwargs.get('suffix', ''))
                filename_ = lsuffix and filename[:-lsuffix] or filename
                filenames = glob.glob(filename_ + '*')
                if len(filename_) < 3 or len(filenames) > 5:
                    # For paranoid yoh who stepped into this already ones ;-)
                    lgr.warning("It is unlikely that it was intended to remove all"
                                " files matching %r. Skipping" % filename_)
                    return
                for f in filenames:
                    try:
                        # Can also be a directory
                        if os.path.isdir(f):
                            shutil.rmtree(f)
                        else:
                            os.unlink(f)
                    except OSError:
                        pass
        newfunc = make_decorator(func)(newfunc)
        return newfunc

    return decorate
