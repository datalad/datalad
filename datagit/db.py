#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
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
#-----------------\____________________________________/------------------

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import json

__db_version__ = '0.0.2'

def load_db(path, allow_unsupported=False):
    with open(path) as f:
        db = json.load(f)
    if not allow_unsupported and db.get('version') != __db_version__:
        raise ValueError("Loaded db from %s is of unsupported version %s. "
                         "Currently supported: %s"
                         % (path, db.get('version'), __db_version__))
    return db

def save_db(db, path):
    if not 'version' in db:
        db['version'] = __db_version__
    assert(sorted(db.keys()) == ['version', 'incoming', 'public_incoming'],
           "Got following db keys %s" % db.keys())
    with open(path, 'w') as f:
        json.dump(db, f, indent=2, sort_keys=True, separators=(',', ': '))
