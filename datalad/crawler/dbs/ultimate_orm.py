# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Ultimate DB ORM"""

"""
I foresee functionality which would use UltimateDB to carry out various actions.
Probably best positioned outside of the DB...?

    URLsVerifier -- to check and/or verify URLs to contain the same load
      This one might want to use Status information for quick verification, which is
      stored in other DBs... Should we also store size/mtime in UltimateDB?
      Probably so -- size for each entry, mtime for each URL.  Some URLs might not provide
      reliable mtime though.
      But really to verify 100% we would need a full download

    URLsUpdater -- given an annex and db, go through the keys (all? for some files? ...) and update
      annex information on urls.

    Upon regular end of crawling we would want to use URLsUpdater to extend/update known
    information
"""

from sqlalchemy.ext.declarative import declarative_base

from datalad.utils import auto_repr

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy import Binary
# only from upcoming 1.1
from sqlalchemy.types import CHAR
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from datalad.support.digests import Digester

INVALID_REASONS = ['NA', 'removed', 'changed', 'denied', 'uuid-mismatch']


DBTable = declarative_base()

# XXX not sure when penalty comes due to our many-to-many relationships
# which might be an additional query etc... depending how/when it is done
# (e.g. if at the request of .files attribute value), we might want to exclude
# those from @auto_repr
@auto_repr
class File(DBTable):
    """
    Binds together information about the file content -- common digests and size
    """
    __tablename__ = 'file'

    id = Column(Integer, primary_key=True)
    size = Column(Integer)  # in Bytes
    # Digests
    # TODO actually each one of them could be stored in half space using BINARY(size/2)
    #     since all those are just hex views of a large number.
    #     We could take advantage of
    #     http://docs.sqlalchemy.org/en/rel_1_0/core/custom_types.html#types-custom
    # As they say "premature optimization is evil" and since DB experience is limited
    # let's do it as simple as possible for now -- full hex strings.
    md5 = Column(CHAR(32), index=True)  # we will more frequently query by md5 and sha256 (Default) so indexing them
    sha1 = Column(CHAR(40))
    sha256 = Column(CHAR(64), index=True, unique=True)  # if we hit collision at this digest -- wooo
    sha512 = Column(CHAR(128), unique=True)
    # TODO ipfs = Column(CHAR(46), unique=True)
    # Additional info from output of file
    content_type = Column(String(256))
    content_charset = Column(String(64))
    # running file -z
    content_type_u = Column(String(256))
    content_charset_u = Column(String(64))

    def get_digests(self):
        """Return a dictionary with digests stored for this file in the DB"""
        return {algo: getattr(self, algo) for algo in Digester.DEFAULT_DIGESTS}


@auto_repr
class Key(DBTable):
    """
    annex keys bound to files.  Sure thing they could be estimated for any
    backend relying on digest backend, but to not poke for what is the right
    one we better maintain one-to-many mapping (while not carrying about tracking
    pure URL etc keys for now at least)
    """
    __tablename__ = 'key'

    id = Column(Integer, primary_key=True)
    key = Column(String(256 + 20 + 10 + 10))  # allowing for variable size, backend name and extensions in E backends

    file_id = Column(Integer, ForeignKey('file.id'))
    # link back to the file and also allocate 1-to-many .keys in File
    file = relationship("File", backref="keys")


@auto_repr
class URL(DBTable):
    """Information about URLs from which a file could be downloaded

    So it is the urls which could be associated with keys in annex.
    For git repositories serving .git/annex/objects via http (so theoretically there
    is a URL per each key), just use  `SpecialRemote(location=url, type='git')`

    XXX??? Should we track "local" urls such as pointing to the content within
    archives???  if so it makes a custom case that we should then maintain key_id
    for the original key from which we could access those... or alternatively we
    could figure that later actually by parsing URL, getting the key, getting to
    actual File and possibly even generating a new URL pointing to the alternative
    key which might already be present in the Repo... yeah, so probably ok to store
    but not worth additional reference.   But may be then we need an additional
    field to discriminate between such 'internal' and "public" URLs?
    """
    __tablename__ = 'url'

    id = Column(Integer, primary_key=True)
    url = Column(String)  # TODO: limit size?  probably not since even standard doesn't really... browsers usually handle up to 2048
    filename = Column(String)  # could differ from the one in URL due to content-disposition etc

    last_modified = Column(DateTime)
    content_type = Column(String(256))  # 127/127   RFC 6838   server might provide different one

    # just checked to be accessible
    first_checked = Column(DateTime)
    last_checked = Column(DateTime)

    # checked to contain the target load
    first_validated = Column(DateTime)
    last_validated = Column(DateTime)

    valid = Column(Boolean)
    last_invalid = Column(DateTime)
    invalid_reason = Column(Enum(*INVALID_REASONS))  #  XXX we might want to use fancy Enum class backported to 2.x?

    file_id = Column(Integer, ForeignKey('file.id'))
    # link back to the file and also allocate 1-to-many .urls in File
    file = relationship("File", backref="urls")


# Later tables establish tracking over repositories available locally or remotely
# E.g. a remote git-annex repository containing annex load would be listed as a
# SpecialRemote type=git with location pointing to e.g. http:// url from where
# annex load could be fetched if necessary.

from sqlalchemy import Table

keys_to_repos = Table(
    'keys_to_repos', DBTable.metadata,
    Column('key_id', Integer, ForeignKey('key.id')),
    Column('repo_id', Integer, ForeignKey('repo.id'))
)


class AnnexRepo(DBTable):
    """
    Base class/structure to track annex repositories -- local or special remotes
    """
    __tablename__ = 'repo'

    id = Column(Integer, primary_key=True)
    # TODO: annex-version?
    type = Column(String(20))   ### git/annex ????

    location = Column(String)
    uuid = Column(CHAR(36))

    last_checked = Column(DateTime)

    valid = Column(Boolean)
    last_invalid = Column(DateTime)
    invalid_reason = Column(Enum(*INVALID_REASONS))  #  XXX we might want to use fancy Enum class backported to 2.x?

    keys = relationship("Key", secondary=keys_to_repos, backref="repos")

    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'repo',
        'with_polymorphic': '*'
    }


@auto_repr
class LocalRepo(AnnexRepo):
    """Local annex repositories"""

    __tablename__ = 'localrepo'

    id = Column(Integer, ForeignKey('repo.id'), primary_key=True)

    bare = Column(Boolean())

    __mapper_args__ = {'polymorphic_identity': 'localrepo'}


@auto_repr
class Dataset(DBTable):

    __tablename__ = 'dataset'

    id = Column(String(36), primary_key=True)
    # link back to repo # and also allocate 1-to-many .datasets in Repo
    repo_id = Column(Integer, ForeignKey('repo.id'))
    # repo = relationship("AnnexRepo", backref="datasets")

# keys_to_specialremotes = Table(
#     'keys_to_specialremotes', DBTable.metadata,
#     Column('key_id', Integer, ForeignKey('key.id')),
#     Column('specialremote_id', Integer, ForeignKey('specialremote.id'))
# )


@auto_repr
class SpecialRemote(AnnexRepo):
    """Special annex remotes"""

    __tablename__ = 'specialremote'

    id = Column(Integer, ForeignKey('repo.id'), primary_key=True)

    name = Column(String)
    remote_type = Column(String(64))  # unlikely to be longer:  s3, git,
    # ??? could options differ among repos for the same special remote?
    options = Column(String())  # actually a dict, so ideally we could use JSON which will be avail in 1.1
                                # for now will encode using ... smth

    __mapper_args__ = {'polymorphic_identity': 'specialremote'}


# TODO:  Dataset -- since we are having repos, we should associate them with Datasets and record those ids

#    keys = relationship("Key", secondary=keys_to_specialremotes, backref="specialremotes")


# TODO?  some kind of "transactions" DB which we possibly purge from time to time???


"""
from sqlalchemy import or_

engine = create_engine('sqlite:///:memory:', echo=True)
def _initiate_tables(engine):
    return DBTable.metadata.create_all(engine)


file = File(md5="a1b23")  # woohoo autorepr works!!!
url = URL(url="http://example.com", file=file)

_initiate_tables(engine)
session = Session(bind=engine)
session.add(url)
session.flush()

print file.id
print repr(file.md5), file, file.urls

print url, url.id
session.query(File).filter_by(md5='a1b23').one().urls
session.query(File).filter(or_(File.sha1==None, File.md5==None)).one()
import q; q.d()
"""
