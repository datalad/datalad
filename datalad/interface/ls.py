# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper utility to list things.  ATM list content of S3 bucket
"""

__docformat__ = 'restructuredtext'

import sys
import time
from os.path import exists, lexists, join as opj, abspath, isabs
from os.path import curdir, isfile, islink, isdir, dirname
from os import readlink, listdir, lstat

from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError

from ..utils import auto_repr
from .base import Interface
from ..ui import ui
from ..utils import swallow_logs
from ..dochelpers import exc_str
from ..support.s3 import get_key_url
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone

from logging import getLogger
lgr = getLogger('datalad.api.ls')


class Ls(Interface):
    """Magical helper to list content of various things (ATM only S3 buckets and datasets)

    Examples
    --------

      $ datalad ls s3://openfmri/tarballs/ds202  # to list S3 bucket
      $ datalad ls .                             # to list current dataset
    """

    _params_ = dict(
        loc=Parameter(
            doc="URL to list, e.g. s3:// url",
            nargs="+",
            constraints=EnsureStr() | EnsureNone(),
        ),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recurse into subdirectories",
        ),
        fast=Parameter(
            args=("-F", "--fast"),
            action="store_true",
            doc="only perform fast operations.  Would be overridden by --all",
        ),
        all=Parameter(
            args=("-a", "--all"),
            action="store_true",
            doc="list all entries, not e.g. only latest entries in case of S3",
        ),
        config_file=Parameter(
            doc="""path to config file which could help the 'ls'.  E.g. for s3://
            URLs could be some ~/.s3cfg file which would provide credentials""",
            constraints=EnsureStr() | EnsureNone()
        ),
        list_content=Parameter(
            choices=(None, 'first10', 'md5', 'full'),
            doc="""list also the content or only first 10 bytes (first10), or md5
            checksum of an entry.  Might require expensive transfer and dump
            binary output to your screen.  Do not enable unless you know what you
            are after""",
            default=None
        ),
        web=Parameter(
            args=("-w", "--web"),
            action="store_true",
            doc="list the content state of the dataset as json for web rendering",
        ),
    )

    @staticmethod
    def __call__(loc, recursive=False, fast=False, all=False, config_file=None, list_content=False, web=False):

        kw = dict(fast=fast, recursive=recursive, all=all)
        if isinstance(loc, list):
            return [Ls.__call__(loc_, config_file=config_file, list_content=list_content, web=web, **kw)
                    for loc_ in loc]

        # TODO: do some clever handling of kwargs as to remember what were defaults
        # and what any particular implementation actually needs, and then issuing
        # warning if some custom value/option was specified which doesn't apply to the
        # given url

        if loc.startswith('s3://'):
            return _ls_s3(loc, config_file=config_file, list_content=list_content, **kw)
        elif lexists(loc):  # and lexists(opj(loc, '.git')):
            # TODO: use some helper like is_dataset_path ??
            return _ls_web(loc, **kw) if web else _ls_dataset(loc, **kw)
        else:
            #raise ValueError("ATM supporting only s3:// URLs and paths to local datasets")
            # TODO: unify all the output here -- _ls functions should just return something
            # to be displayed
            ui.message(
                "%s%s%s  %sunknown%s"
                % (LsFormatter.BLUE, loc, LsFormatter.RESET, LsFormatter.RED, LsFormatter.RESET))


#
# Dataset listing
#

from datalad.support.annexrepo import AnnexRepo
from datalad.support.annexrepo import GitRepo


@auto_repr
class DsModel(object):

    __slots__ = ['ds', '_info', '_path', '_branch']

    def __init__(self, ds):
        self.ds = ds
        self._info = None
        self._path = None  # can be overriden
        self._branch = None

    @property
    def path(self):
        return self.ds.path if self._path is None else self._path

    @path.setter
    def path(self, v):
        self._path = v

    @property
    def repo(self):
        return self.ds.repo

    @property
    def describe(self):
        try:
            with swallow_logs():
                describe, outerr = self.repo._git_custom_command([], ['git', 'describe', '--tags'])
            return describe.strip()
        except:
            return None

    @property
    def date(self):
        """Date of the last commit
        """
        try:
            commit = next(self.repo.get_branch_commits(self.branch))
        except:
            return None
        return commit.committed_date

    @property
    def clean(self):
        return not self.repo.dirty

    @property
    def branch(self):
        if self._branch is None:
            try:
                self._branch = self.repo.get_active_branch()
            except:
                return None
        return self._branch

    @property
    def type(self):
        if not exists(self.ds.path):
            return None
        return {False: 'git', True: 'annex'}[isinstance(self.repo, AnnexRepo)]

    @property
    def info(self):
        if self._info is None and isinstance(self.repo, AnnexRepo):
            self._info = self.repo.repo_info()
        return self._info

    @property
    def annex_worktree_size(self):
        info = self.info
        return info['size of annexed files in working tree'] if info else None

    @property
    def annex_local_size(self):
        info = self.info
        return info['local annex size'] if info else None


@auto_repr
class FsModel(DsModel):

    __slots__ = ['_path', '_info', '_repo']

    def __init__(self, path, repo=""):
        self._path = path  # can be overridden
        self._info = None
        self._repo = repo
        self._branch = None

    @property
    def _symlink(self):
        if islink(self._path):                    # if symlink
            target_path = readlink(self._path)    # find link target
            # convert to absolute path if not
            target_path = opj(dirname(self._path), target_path) if not isabs(target_path) else target_path
            return target_path if exists(target_path) else False
        return False

    @property
    def repo(self):
        if exists(opj(self._repo, ".git", "annex")):
            return AnnexRepo(self._repo)
        elif exists(opj(self._repo, ".git")):
            return GitRepo(self._repo)
        else:
            return None

    @property
    def date(self):
        """Date of last modification
        """
        if self._type is not ['git', 'annex']:
            return lstat(self._path).st_mtime
        else:
            super(self.__class__, self).date

    @property
    def size(self):
        _type = self._type
        if not _type:
            return -1
        if 'annex' in _type:
            return self.annex_local_size
        elif 'git' in _type:
            return self.git_local_size
        elif 'file' in _type:
            return lstat(self._path).st_size
        elif 'broken-link' in _type:
            return 0
        elif 'link' in _type:
            return lstat(self._symlink).st_size
        elif 'dir' in _type:
            return lstat(self._path).st_size  # add du -s command for plain dir
        else:
            return -1

    @property
    def _type(self):
        if islink(self.path):
            return 'broken-link' if not self._symlink else 'link'
        elif isfile(self.path):
            return 'file'
        elif exists(opj(self.path, ".git", "annex")):
            return 'annex'
        elif exists(opj(self.path, ".git")):
            return 'git'
        elif isdir(self.path):
            return 'dir'
        else:
            return None

    @property
    def git_local_size(self):
        try:
            describe, outerr = self.repo._git_custom_command([], ['git', 'count-objects', '-v'])[0].split('\n')
            size = [item for item in describe if 'size: ' in item][0].split(': ')
            return int(size[1])
        except:
            return lstat(self._path).st_size

import string
import humanize
from datalad.log import ColorFormatter
from datalad.utils import is_interactive

class LsFormatter(string.Formatter):
    # condition by interactive
    if is_interactive():
        BLUE = ColorFormatter.COLOR_SEQ % (ColorFormatter.BLUE + 30)
        RED = ColorFormatter.COLOR_SEQ % (ColorFormatter.RED + 30)
        GREEN = ColorFormatter.COLOR_SEQ % (ColorFormatter.GREEN + 30)
        RESET = ColorFormatter.RESET_SEQ
    else:
        BLUE = RED = GREEN = RESET = u""

    # http://stackoverflow.com/questions/9932406/unicodeencodeerror-only-when-running-as-a-cron-job
    # reveals that Python uses ascii encoding when stdout is a pipe, so we shouldn't force it to be
    # unicode then
    # TODO: we might want to just ignore and force utf8 while explicitly .encode()'ing output!
    if sys.getdefaultencoding() == 'ascii':
        OK = 'OK'   # u"✓"
        NOK = 'X'  # u"✗"
        NONE = '-'  # u"✗"
    else:
        # unicode versions which look better but which blow during tests etc
        OK = u"✓"
        NOK = u"✗"
        NONE = u"✗"

    def convert_field(self, value, conversion):
        #print("%r->%r" % (value, conversion))
        if conversion == 'D':  # Date
            if value is not None:
                return time.strftime(u"%Y-%m-%d/%H:%M:%S", time.localtime(value))
            else:
                return u'-'
        elif conversion == 'S':  # Human size
            #return value
            if value is not None:
                return humanize.naturalsize(value)
            else:
                return u'-'
        elif conversion == 'X':  # colored bool
            chr, col = (self.OK, self.GREEN) if value else (self.NOK, self.RED)
            return u"%s%s%s" % (col, chr, self.RESET)
        elif conversion == 'N':  # colored Red - if None
            if value is None:
                # return "%s✖%s" % (self.RED, self.RESET)
                return u"%s%s%s" % (self.RED, self.NONE, self.RESET)
            return value
        elif conversion in {'B', 'R'}:
            return u"%s%s%s" % ({'B': self.BLUE, 'R': self.RED}[conversion], value, self.RESET)

        return super(LsFormatter, self).convert_field(value, conversion)


def format_ds_model(formatter, ds_model, format_str, format_exc):
    try:
        #print("WORKING ON %s" % ds_model.path)
        if not exists(ds_model.ds.path) or not ds_model.ds.repo:
            return formatter.format(format_exc, ds=ds_model, msg=u"not installed")
        ds_formatted = formatter.format(format_str, ds=ds_model)
        #print("FINISHED ON %s" % ds_model.path)
        return ds_formatted
    except Exception as exc:
        return formatter.format(format_exc, ds=ds_model, msg=exc_str(exc))

# from joblib import Parallel, delayed

def _ls_dataset(loc, fast=False, recursive=False, all=False):
    from ..distribution.dataset import Dataset
    isabs_loc = isabs(loc)
    topdir = '' if isabs_loc else abspath(curdir)

    topds = Dataset(loc)
    dss = [topds] + (
        [Dataset(opj(loc, sm))
         for sm in topds.get_dataset_handles(recursive=recursive)]
        if recursive else [])
    dsms = list(map(DsModel, dss))

    # adjust path strings
    for ds_model in dsms:
        path = ds_model.path[len(topdir) + 1 if topdir else 0:]
        if not path:
            path = '.'
        ds_model.path = path

    maxpath = max(len(ds_model.path) for ds_model in dsms)
    path_fmt = u"{ds.path!B:<%d}" % (maxpath + (11 if is_interactive() else 0))  # + to accommodate ansi codes
    pathtype_fmt = path_fmt + u"  [{ds.type}]"
    full_fmt = pathtype_fmt + u"  {ds.branch!N}  {ds.describe!N} {ds.date!D}"
    if (not fast) or all:
        full_fmt += u"  {ds.clean!X}"
    if all:
        full_fmt += u"  {ds.annex_local_size!S}/{ds.annex_worktree_size!S}"

    formatter = LsFormatter()
    # weird problems happen in the parallel run -- TODO - figure it out
    # for out in Parallel(n_jobs=1)(
    #         delayed(format_ds_model)(formatter, dsm, full_fmt, format_exc=path_fmt + "  {msg!R}")
    #         for dsm in dss):
    #     print(out)
    for dsm in dsms:
        ds_str = format_ds_model(formatter, dsm, full_fmt, format_exc=path_fmt + u"  {msg!R}")
        print(ds_str)


def JsonFormatter(path, repo, _type, size, date):
    pretty_size = humanize.naturalsize(size)
    pretty_date = time.strftime(u"%Y-%m-%d/%H:%M:%S", time.localtime(date))
    json_fmt = u'{\"path\": \"%s\", \"repo\": \"%s\", \"type\": \"%s\", \"size\": \"%s\", \"date\": \"%s\"}'
    return json_fmt % (path, repo, _type, pretty_size, pretty_date)


def _flatten(listoflists):
    """flattens a multi-level lists"""
    if isinstance(listoflists, list):
        flatlist = []
        for item in listoflists:
            if isinstance(item, list):
                flatlist.extend(_flatten(item))
            else:
                flatlist.append(item)
        return flatlist
    else:
        return listoflists


def _fs_traverse(loc, recursive=False):
    """takes a path and returns a list of (not git/annex) nodes
    """
    # if node is a file, symlink or under git or git_annex
    if isfile(loc) or islink(loc) or isdir(opj(loc, ".git")) or isdir(opj(loc, ".git", "annex")):
        return [loc]
    # else if plain directory
    elif isdir(loc):
        f = [loc]
        if recursive:
            f.extend(_flatten(_fs_traverse(opj(loc, node), recursive=recursive) for node in listdir(loc)))
        else:
            f.extend([opj(loc, node) for node in listdir(loc)])
        return f


def _ls_web(loc, fast=False, recursive=False, all=False):
    from ..distribution.dataset import Dataset
    isabs_loc = isabs(loc)
    topdir = '' if isabs_loc else abspath(curdir)

    topds = Dataset(loc)
    dss = [topds] + (
        [Dataset(opj(loc, sm))
         for sm in topds.get_dataset_handles(recursive=recursive)]
        if recursive else [])
    dsms = list(map(DsModel, dss))

    # adjust path strings
    fs = []
    for ds_model in dsms:
        path = ds_model.path[len(topdir) + 1 if topdir else 0:]
        if not path:
            path = '.'
        ds_model.path = path
        # unwrap top git directory and run traversal on each non .git node
        fs.append(_flatten([path, [_fs_traverse(subdir, recursive=True)
                                   for subdir in listdir(path)
                                   if '.git' not in subdir]]))

    # attach the FSModel to each node in the traversed fs tree
    fsm = [FsModel(node, fss[0]) for fss in fs for node in fss]
    print '[' + JsonFormatter(fsm[0]._path, fsm[0]._repo, fsm[0]._type, fsm[0].size, fsm[0].date)
    for item in fsm[1:]:
        print ', ' + JsonFormatter(item._path, item._repo, item._type, item.size, item.date)
    print ']'

#
# S3 listing
#

def _ls_s3(loc, fast=False, recursive=False, all=False, config_file=None, list_content=False):
    """List S3 bucket content"""
    if loc.startswith('s3://'):
        bucket_prefix = loc[5:]
    else:
        raise ValueError("passed location should be an s3:// url")

    import boto
    from hashlib import md5
    from boto.s3.key import Key
    from boto.s3.prefix import Prefix
    from boto.exception import S3ResponseError
    from ..support.configparserinc import SafeConfigParser  # provides PY2,3 imports

    bucket_name, prefix = bucket_prefix.split('/', 1)

    if '?' in prefix:
        ui.message("We do not care about URL options ATM, they get stripped")
        prefix = prefix[:prefix.index('?')]

    ui.message("Connecting to bucket: %s" % bucket_name)
    if config_file:
        config = SafeConfigParser(); config.read(config_file)
        access_key = config.get('default', 'access_key')
        secret_key = config.get('default', 'secret_key')

        # TODO: remove duplication -- reuse logic within downloaders/s3.py to get connected
        conn = boto.connect_s3(access_key, secret_key)
        try:
            bucket = conn.get_bucket(bucket_name)
        except S3ResponseError as e:
            ui.message("E: Cannot access bucket %s by name" % bucket_name)
            all_buckets = conn.get_all_buckets()
            all_bucket_names = [b.name for b in all_buckets]
            ui.message("I: Found following buckets %s" % ', '.join(all_bucket_names))
            if bucket_name in all_bucket_names:
                bucket = all_buckets[all_bucket_names.index(bucket_name)]
            else:
                raise RuntimeError("E: no bucket named %s thus exiting" % bucket_name)
    else:
        # TODO: expose credentials
        # We don't need any provider here really but only credentials
        from datalad.downloaders.providers import Providers
        providers = Providers.from_config_files()
        provider = providers.get_provider(loc)
        if not provider:
            raise ValueError("don't know how to deal with this url %s -- no downloader defined.  "
                             "Specify just s3cmd config file instead")
        bucket = provider.authenticator.authenticate(bucket_name, provider.credential)

    info = []
    for iname, imeth in [
        ("Versioning", bucket.get_versioning_status),
        ("   Website", bucket.get_website_endpoint),
        ("       ACL", bucket.get_acl),
    ]:
        try:
            ival = imeth()
        except Exception as e:
            ival = str(e).split('\n')[0]
        info.append(" {iname}: {ival}".format(**locals()))
    ui.message("Bucket info:\n %s" % '\n '.join(info))

    kwargs = {} if recursive else {'delimiter': '/'}
    prefix_all_versions = list(bucket.list_versions(prefix, **kwargs))

    if not prefix_all_versions:
        ui.error("No output was provided for prefix %r" % prefix)
    else:
        max_length = max((len(e.name) for e in prefix_all_versions))
    for e in prefix_all_versions:
        if isinstance(e, Prefix):
            ui.message("%s" % (e.name, ),)
            continue
        ui.message(("%%-%ds %%s" % max_length) % (e.name, e.last_modified), cr=' ')
        if isinstance(e, Key):
            if not (e.is_latest or all):
                # Skip this one
                continue
            url = get_key_url(e, schema='http')
            try:
                _ = urlopen(Request(url))
                urlok = "OK"
            except HTTPError as err:
                urlok = "E: %s" % err.code

            try:
                acl = e.get_acl()
            except S3ResponseError as err:
                acl = err.message

            content = ""
            if list_content:
                # IO intensive, make an option finally!
                try:
                    # _ = e.next()[:5]  if we are able to fetch the content
                    kwargs = dict(version_id=e.version_id)
                    if list_content in {'full', 'first10'}:
                        if list_content in 'first10':
                            kwargs['headers'] = {'Range': 'bytes=0-9'}
                        content = repr(e.get_contents_as_string(**kwargs))
                    elif list_content == 'md5':
                        digest = md5()
                        digest.update(e.get_contents_as_string(**kwargs))
                        content = digest.hexdigest()
                    else:
                        raise ValueError(list_content)
                    # content = "[S3: OK]"
                except S3ResponseError as err:
                    content = err.message
                finally:
                    content = " " + content

            ui.message("ver:%-32s  acl:%s  %s [%s]%s" % (e.version_id, acl, url, urlok, content))
        else:
            if all:
                ui.message("del")
