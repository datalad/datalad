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

import shutil, stat, os

from ..cmd import getstatusoutput

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
                status, output = getstatusoutput(
                    'cd %(path)s && tar -czvf %(name)s %(dirname)s' % locals())
                # remove original tree
                shutil.rmtree(full_dirname)
            else:
                create_tree(full_name, load)
        else:
            with open(full_name, 'w') as f:
                f.write(load)

def with_tree(tree, **tkwargs):
    def decorate(func):
        def newfunc(*arg, **kw):
            d = tempfile.mkdtemp(**tkwargs)
            create_tree(d, tree)
            try:
                func(*(arg + (d,)), **kw)
            finally:
                #print "TODO: REMOVE tree ", d
                shutil.rmtree(d)

        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate


# GRRR -- this one is crippled since path where HTTPServer is serving
# from can't be changed without pain.

import SimpleHTTPServer
import SocketServer
from threading import Thread

def serve_path_via_http(*args, **tkwargs):
    def decorate(func):
        def newfunc(path, *arg, **kw):
            port = 8006
            #print "Starting to serve path ", path
            # TODO: ATM we are relying on path being local so we could
            # start HTTP server in the same directory.  FIX IT!
            SocketServer.TCPServer.allow_reuse_address = True
            httpd = SocketServer.TCPServer(("", port),
                        SimpleHTTPServer.SimpleHTTPRequestHandler)
            server_thread = Thread(target=httpd.serve_forever)
            server_thread.start()
            #time.sleep(1)               # just give it few ticks
            try:
                func(*(('http://localhost:%d/%s/' % (port, path),)+arg), **kw)
            finally:
                #print "Stopping server"
                httpd.shutdown()
                #print "Waiting for thread to stop"
                server_thread.join()
        newfunc = make_decorator(func)(newfunc)
        return newfunc
    return decorate
