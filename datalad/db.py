# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

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
    assert set(db.keys()) == set(['incoming', 'public_incoming', 'version']), \
           "Got following db keys %s" % db.keys()
    with open(path, 'w') as f:
        json.dump(db, f, indent=2, sort_keys=True, separators=(',', ': '))
