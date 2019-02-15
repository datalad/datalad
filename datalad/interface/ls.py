# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper utility to list things.  ATM lists datasets and S3 bucket URLs
"""
__docformat__ = 'restructuredtext'

import humanize
import sys
import string
import time

from os.path import exists, lexists, join as opj, abspath, isabs
from os.path import curdir, isfile, islink, isdir, realpath
from os.path import relpath
from os import lstat

from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError

from ..utils import auto_repr
from .base import Interface
from datalad.interface.base import build_doc
from ..ui import ui
from ..utils import safe_print
from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support import ansi_colors
from ..support.constraints import EnsureStr, EnsureNone
from ..distribution.dataset import Dataset

from datalad.support.annexrepo import AnnexRepo
from datalad.support.annexrepo import GitRepo
from datalad.utils import is_interactive

from logging import getLogger
lgr = getLogger('datalad.api.ls')


@build_doc
class Ls(Interface):
    """List summary information about URLs and dataset(s)

    ATM only s3:// URLs and datasets are supported

    Examples:

      $ datalad ls s3://openfmri/tarballs/ds202  # to list S3 bucket
      $ datalad ls                               # to list current dataset
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

    # TODO: during big RF refactor this one away since it must not be instance's
    # attribute.  For now introduced to make `datalad ls` be relatively usable
    # in terms of speed
    _cached_subdatasets = {}

    _params_ = dict(
        loc=Parameter(
            doc="URL or path to list, e.g. s3://...",
            metavar='PATH/URL',
            nargs="*",
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
        all_=Parameter(
            args=("-a", "--all"),
            dest='all_',
            action="store_true",
            doc="list all (versions of) entries, not e.g. only latest entries "
                "in case of S3",
        ),
        long_=Parameter(
            args=("-L", "--long"),
            dest='long_',
            action="store_true",
            doc="list more information on entries (e.g. acl, urls in s3, annex "
                "sizes etc)",
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
        json=Parameter(
            choices=('file', 'display', 'delete'),
            doc="""metadata json of dataset for creating web user interface.
            display: prints jsons to stdout or
            file: writes each subdir metadata to json file in subdir of dataset or
            delete: deletes all metadata json files in dataset""",
        ),
    )

    @staticmethod
    def __call__(loc, recursive=False, fast=False, all_=False, long_=False,
                 config_file=None, list_content=False, json=None):
        if json:
            from datalad.interface.ls_webui import _ls_json

        if isinstance(loc, list) and not len(loc):
            # nothing given, CWD assumed -- just like regular ls
            loc = '.'

        kw = dict(fast=fast, recursive=recursive, all_=all_, long_=long_)
        if isinstance(loc, list):
            return [Ls.__call__(loc_, config_file=config_file,
                                list_content=list_content, json=json, **kw)
                    for loc_ in loc]

        # TODO: do some clever handling of kwargs as to remember what were defaults
        # and what any particular implementation actually needs, and then issuing
        # warning if some custom value/option was specified which doesn't apply to the
        # given url

        # rename to not angry Python gods who took all_ good words
        kw['long_'] = kw.pop('long_')

        loc_type = "unknown"
        if loc.startswith('s3://'):
            return _ls_s3(loc, config_file=config_file, list_content=list_content,
                          **kw)
        elif lexists(loc):
            if isdir(loc):
                ds = Dataset(loc)
                if ds.is_installed():
                    return _ls_json(loc, json=json, **kw) if json else _ls_dataset(loc, **kw)
                    loc_type = False
                else:
                    loc_type = "dir"  # we know that so far for sure
                    # it might have been an uninstalled dataset within super-dataset
                    superds = ds.get_superdataset()
                    if superds:
                        try:
                            subdatasets = Ls._cached_subdatasets[superds.path]
                        except KeyError:
                            subdatasets = Ls._cached_subdatasets[superds.path] \
                                = superds.subdatasets(result_xfm='relpaths')
                        if relpath(ds.path, superds.path) in subdatasets:
                            loc_type = "not installed"
            else:
                loc_type = "file"
                # could list properties -- under annex or git, either clean/dirty
                # etc
                # repo = get_repo_instance(dirname(loc))

        if loc_type:
            #raise ValueError("ATM supporting only s3:// URLs and paths to local datasets")
            # TODO: unify all_ the output here -- _ls functions should just return something
            # to be displayed
            ui.message(
                "{}  {}".format(
                    ansi_colors.color_word(loc, ansi_colors.DATASET),
                    ansi_colors.color_word(
                        loc_type,
                        ansi_colors.RED
                        if loc_type in {'unknown', 'not installed'}
                        else ansi_colors.BLUE)
                )
            )


#
# Dataset listing
#

@auto_repr
class AbsentRepoModel(object):
    """Just a base for those where repo wasn't installed yet"""

    def __init__(self, path):
        self.path = path
        self.repo = None

    @property
    def type(self):
        return "N/A"


@auto_repr
class GitModel(object):
    """A base class for models which have some .repo available"""

    __slots__ = ['_branch', 'repo', '_path']

    def __init__(self, repo):
        self.repo = repo
        # lazy evaluation variables
        self._branch = None
        self._path = None

    @property
    def path(self):
        return self.repo.path if self._path is None else self._path

    @path.setter
    def path(self, v):
        self._path = v

    @property
    def branch(self):
        if self._branch is None:
            try:
                self._branch = self.repo.get_active_branch()
            except:  # MIH: InvalidGitRepositoryError?
                return None
        return self._branch

    @property
    def clean(self):
        return not self.repo.dirty

    @property
    def describe(self):
        return self.repo.describe(tags=True)

    @property
    def date(self):
        """Date of the last commit
        """
        return self.repo.get_commit_date()

    @property
    def count_objects(self):
        return self.repo.count_objects

    @property
    def git_local_size(self):
        count_objects = self.count_objects
        return count_objects['size'] if count_objects else None

    @property
    def type(self):
        return {False: 'git', True: 'annex'}[isinstance(self.repo, AnnexRepo)]


@auto_repr
class AnnexModel(GitModel):

    __slots__ = ['_info'] + GitModel.__slots__

    def __init__(self, *args, **kwargs):
        super(AnnexModel, self).__init__(*args, **kwargs)
        self._info = None

    @property
    def info(self):
        if self._info is None and self.type == 'annex':
            # we do not care about descriptions - just about sizes etc,
            # so to allow RO mode operation - disallow git-annex branch
            # merges
            self._info = self.repo.repo_info(merge_annex_branches=False)
        return self._info

    @property
    def annex_worktree_size(self):
        info = self.info
        return info['size of annexed files in working tree'] if info else 0.0

    @property
    def annex_local_size(self):
        info = self.info
        return info['local annex size'] if info else 0.0


@auto_repr
class FsModel(AnnexModel):

    __slots__ = AnnexModel.__slots__

    def __init__(self, path, *args, **kwargs):
        super(FsModel, self).__init__(*args, **kwargs)
        self._path = path

    @property
    def path(self):
        return self._path

    @property
    def symlink(self):
        """if symlink returns path the symlink points to else returns None"""
        if islink(self._path):                    # if symlink
            target_path = realpath(self._path)    # find link target
            # convert to absolute path if not
            return target_path if exists(target_path) else None
        return None

    @property
    def date(self):
        """Date of last modification"""
        if self.type_ is not ['git', 'annex']:
            return lstat(self._path).st_mtime
        else:
            return super(self.__class__, self).date

    @property
    def size(self):
        """Size of the node computed based on its type"""
        type_ = self.type_
        sizes = {'total': 0.0,
                 'ondisk': 0.0,
                 'git': 0.0,
                 'annex': 0.0,
                 'annex_worktree': 0.0}

        if type_ in ['file', 'link', 'link-broken']:
            # if node is under annex, ask annex for node size, ondisk_size
            if isinstance(self.repo, AnnexRepo) and self.repo.is_under_annex(self._path):
                size = self.repo.info(self._path, batch=True)['size']
                ondisk_size = size \
                    if self.repo.file_has_content(self._path) \
                    else 0
            # else ask fs for node size (= ondisk_size)
            else:
                size = ondisk_size = 0 \
                    if type_ == 'link-broken' \
                    else lstat(self.symlink or self._path).st_size

            sizes.update({'total': size, 'ondisk': ondisk_size})

        if self.repo.path == self._path:
            sizes.update({'git': self.git_local_size,
                          'annex': self.annex_local_size,
                          'annex_worktree': self.annex_worktree_size})
        return sizes

    @property
    def type_(self):
        """outputs the node type

        Types: link, link-broken, file, dir, annex-repo, git-repo"""
        if islink(self.path):
            return 'link' if self.symlink else 'link-broken'
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


class LsFormatter(string.Formatter):
    # condition by interactive
    if is_interactive():
        BLUE = ansi_colors.COLOR_SEQ % ansi_colors.BLUE
        RED = ansi_colors.COLOR_SEQ % ansi_colors.RED
        GREEN = ansi_colors.COLOR_SEQ % ansi_colors.GREEN
        RESET = ansi_colors.RESET_SEQ
        DATASET = ansi_colors.COLOR_SEQ % ansi_colors.UNDERLINE
    else:
        BLUE = RED = GREEN = RESET = DATASET = u""

    # TODO: we might want to just ignore and force utf8 while explicitly .encode()'ing output!
    # unicode versions which look better but which blow during tests etc
    # Those might be reset by the constructor
    OK = 'OK'   # u"✓"
    NOK = 'X'  # u"✗"
    NONE = '-'  # u"✗"

    def __init__(self, *args, **kwargs):
        super(LsFormatter, self).__init__(*args, **kwargs)
        if sys.stdout.encoding is None:
            lgr.debug("encoding not set, using safe alternatives")
        elif not sys.stdout.isatty():
            lgr.debug("stdout is not a tty, using safe alternatives")
        else:
            try:
                u"✓".encode(sys.stdout.encoding)
            except UnicodeEncodeError:
                lgr.debug("encoding %s does not support unicode, "
                          "using safe alternatives",
                          sys.stdout.encoding)
            else:
                self.OK = u"✓"
                self.NOK = u"✗"
                self.NONE = u"✗"

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
        elif conversion in {'B', 'R', 'U'}:
            return u"%s%s%s" % ({'B': self.BLUE, 'R': self.RED, 'U': self.DATASET}[conversion], value, self.RESET)

        return super(LsFormatter, self).convert_field(value, conversion)

    def format_field(self, value, format_spec):
        # TODO: move all the "coloring" into formatting, so we could correctly indent
        # given the format and only then color it up
        # print "> %r, %r" % (value, format_spec)
        return super(LsFormatter, self).format_field(value, format_spec)


def format_ds_model(formatter, ds_model, format_str, format_exc):
    try:
        #print("WORKING ON %s" % ds_model.path)
        if not exists(ds_model.path) or not ds_model.repo:
            return formatter.format(format_exc, ds=ds_model, msg=u"not installed")
        ds_formatted = formatter.format(format_str, ds=ds_model)
        #print("FINISHED ON %s" % ds_model.path)
        return ds_formatted
    except Exception as exc:
        return formatter.format(format_exc, ds=ds_model, msg=exc_str(exc))

# from joblib import Parallel, delayed


def _ls_dataset(loc, fast=False, recursive=False, all_=False, long_=False):
    isabs_loc = isabs(loc)
    topdir = '' if isabs_loc else abspath(curdir)

    topds = Dataset(loc)
    dss = [topds] + (
        [Dataset(opj(loc, sm))
         for sm in topds.subdatasets(recursive=recursive, result_xfm='relpaths')]
        if recursive else [])

    dsms = []
    for ds in dss:
        if not ds.is_installed():
            dsm = AbsentRepoModel(ds.path)
        elif isinstance(ds.repo, AnnexRepo):
            dsm = AnnexModel(ds.repo)
        elif isinstance(ds.repo, GitRepo):
            dsm = GitModel(ds.repo)
        else:
            raise RuntimeError("Got some dataset which don't know how to handle %s"
                               % ds)
        dsms.append(dsm)

    # adjust path strings
    for ds_model in dsms:
        #path = ds_model.path[len(topdir) + 1 if topdir else 0:]
        path = relpath(ds_model.path, topdir) if topdir else ds_model.path
        if not path:
            path = '.'
        ds_model.path = path
    dsms = sorted(dsms, key=lambda m: m.path)

    maxpath = max(len(ds_model.path) for ds_model in dsms)
    path_fmt = u"{ds.path!U:<%d}" % (maxpath + (11 if is_interactive() else 0))  # + to accommodate ansi codes
    pathtype_fmt = path_fmt + u"  [{ds.type}]"
    full_fmt = pathtype_fmt + u"  {ds.branch!N}  {ds.describe!N} {ds.date!D}"
    if (not fast) or long_:
        full_fmt += u"  {ds.clean!X}"

    fmts = {
        AbsentRepoModel: pathtype_fmt,
        GitModel: full_fmt,
        AnnexModel: full_fmt
    }
    if long_:
        fmts[AnnexModel] += u"  {ds.annex_local_size!S}/{ds.annex_worktree_size!S}"

    formatter = LsFormatter()
    # weird problems happen in the parallel run -- TODO - figure it out
    # for out in Parallel(n_jobs=1)(
    #         delayed(format_ds_model)(formatter, dsm, full_fmt, format_exc=path_fmt + "  {msg!R}")
    #         for dsm in dss):
    #     print(out)
    for dsm in dsms:
        fmt = fmts[dsm.__class__]
        ds_str = format_ds_model(formatter, dsm, fmt, format_exc=path_fmt + u"  {msg!R}")
        safe_print(ds_str)
        # workaround for explosion of git cat-file --batch processes
        # https://github.com/datalad/datalad/issues/1888
        if dsm.repo is not None:
            dsm.repo.repo.close()
            del dsm.repo
            dsm.repo = None


#
# S3 listing
#
def _ls_s3(loc, fast=False, recursive=False, all_=False, long_=False,
           config_file=None, list_content=False):
    """List S3 bucket content"""
    if loc.startswith('s3://'):
        bucket_prefix = loc[5:]
    else:
        raise ValueError("passed location should be an s3:// url")

    import boto
    from hashlib import md5
    from boto.s3.key import Key
    from boto.s3.prefix import Prefix
    from boto.s3.connection import OrdinaryCallingFormat
    from boto.exception import S3ResponseError
    from ..support.configparserinc import SafeConfigParser  # provides PY2,3 imports

    if '/' in bucket_prefix:
        bucket_name, prefix = bucket_prefix.split('/', 1)
    else:
        bucket_name, prefix = bucket_prefix, None

    if prefix and '?' in prefix:
        ui.message("We do not care about URL options ATM, they get stripped")
        prefix = prefix[:prefix.index('?')]

    ui.message("Connecting to bucket: %s" % bucket_name)
    if config_file:
        config = SafeConfigParser()
        config.read(config_file)
        access_key = config.get('default', 'access_key')
        secret_key = config.get('default', 'secret_key')

        # TODO: remove duplication -- reuse logic within downloaders/s3.py to get connected
        kwargs = {}
        if '.' in bucket_name:
            kwargs['calling_format']=OrdinaryCallingFormat()
        conn = boto.connect_s3(access_key, secret_key, **kwargs)
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
            raise ValueError(
                "Don't know how to deal with this url %s -- no provider defined for %s. "
                "Define a new provider (DOCS: TODO) or specify just s3cmd config file instead for now."
                % loc
            )
        downloader = provider.get_downloader(loc)

        # should authenticate etc, and when ready we will ask for a bucket ;)
        bucket = downloader.access(lambda url: downloader.bucket, loc)

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

    ACCESS_METHODS = [
        bucket.list_versions,
        bucket.list
    ]

    prefix_all_versions = None
    got_versioned_list = False
    for acc in ACCESS_METHODS:
        try:
            prefix_all_versions = list(acc(prefix, **kwargs))
            got_versioned_list = acc is bucket.list_versions
            break
        except Exception as exc:
            lgr.debug("Failed to access via %s: %s", acc, exc_str(exc))

    if not prefix_all_versions:
        ui.error("No output was provided for prefix %r" % prefix)
    else:
        max_length = max((len(e.name) for e in prefix_all_versions))
        max_size_length = max((len(str(getattr(e, 'size', 0))) for e in prefix_all_versions))

    results = []
    for e in prefix_all_versions:
        results.append(e)
        if isinstance(e, Prefix):
            ui.message("%s" % (e.name, ),)
            continue

        base_msg = ("%%-%ds %%s" % max_length) % (e.name, e.last_modified)
        if isinstance(e, Key):
            if got_versioned_list and not (e.is_latest or all_):
                lgr.debug(
                    "Skipping Key since not all versions requested: %s", e)
                # Skip this one
                continue
            ui.message(base_msg + " %%%dd" % max_size_length % e.size, cr=' ')
            # OPT: delayed import
            from ..support.s3 import get_key_url
            url = get_key_url(e, schema='http')
            try:
                _ = urlopen(Request(url))
                urlok = "OK"
            except HTTPError as err:
                urlok = "E: %s" % err.code

            try:
                acl = e.get_acl()
            except S3ResponseError as exc:
                acl = exc.code if exc.code in ('AccessDenied',) else str(exc)

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
                    content = str(err)
                finally:
                    content = " " + content
            ui.message(
                "ver:%-32s  acl:%s  %s [%s]%s"
                % (getattr(e, 'version_id', None),
                   acl, url, urlok, content)
                if long_ else ''
            )
        else:
            ui.message(base_msg + " " + str(type(e)).split('.')[-1].rstrip("\"'>"))
    return results
