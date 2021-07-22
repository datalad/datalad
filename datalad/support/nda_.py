# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various supporting utilities to interface with NIMH Data Archive (NDA)

Primary "ugliness" is the requirement of the cx_Oracle (itself is open, but relies
on closed SDK/libraries) module to access miNDAR database.
"""

__docformat__ = 'restructuredtext'

from datalad import cfg
from datalad.downloaders.providers import Providers

from logging import getLogger
lgr = getLogger('datalad.support.nda')

DEFAULT_SERVER = 'mindarvpc.cqahbwk3l1mb.us-east-1.rds.amazonaws.com'

from collections import namedtuple

# Could be extracted from the dictionary
#  https://ndar.nih.gov/api/datadictionary/v2/datastructure/image03
# where type is File
image03_file_fields = [
    'image_file',
    'data_file2'
]
image03_fields = [
    'collection_id',
    'submission_id',
    'dataset_id',
    'experiment_id',
    # 'subjectkey',
    # 'src_subject_id',
] + image03_file_fields

image03_Record = namedtuple('image03_Record', image03_fields)


def get_oracle_db(
        dbserver=None,
        port=1521,
        sid='ORCL',
        credential=None):
    dbserver = dbserver or cfg.obtain('datalad.externals.nda.dbserver',
                                      default=DEFAULT_SERVER)
    # This specific username has access to the 'Image' selection of NDA as of about today
    #username = username \
    #           or cfg.get('externals:nda', 'username',
    #                default='halchenkoy_103924')
    if not credential:
        providers = Providers.from_config_files()
        credential = providers.get_provider(DEFAULT_SERVER).credential

    if not isinstance(credential, dict):
        credential = credential()

    import cx_Oracle   # you must have the beast if you want to access the dark side
    dsnStr = cx_Oracle.makedsn(dbserver, port, sid)
    db = cx_Oracle.connect(user=credential['user'],
                           password=credential['password'],
                           dsn=dsnStr)

    return db
