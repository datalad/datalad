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
                dirname = name[:-7]
                full_dirname = os.path.join(path, dirname)
                os.makedirs(full_dirname)
                create_tree(full_dirname, load)
                # create archive
                status, output = Runner().getstatusoutput(
                    'cd %(path)s && tar -czvf %(name)s %(dirname)s' % locals())
                # remove original tree
                shutil.rmtree(full_dirname)
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
