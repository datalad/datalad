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
from os.path import exists, lexists, join as opj, abspath, isabs, getmtime
from os.path import curdir, isfile, islink, isdir, dirname, basename, split, realpath
from os.path import relpath
from os import listdir, lstat, remove, makedirs
import json as js
import hashlib

from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError

from ..cmdline.helpers import get_repo_instance
from ..utils import auto_repr
from .base import Interface
from ..ui import ui
from ..utils import swallow_logs
from ..consts import METADATA_DIR
from ..consts import METADATA_FILENAME
from ..dochelpers import exc_str
from ..support.param import Parameter
from ..support import ansi_colors
from ..support.constraints import EnsureStr, EnsureNone
from ..distribution.dataset import Dataset

from datalad.support.annexrepo import AnnexRepo
from datalad.support.annexrepo import GitRepo

import string
import humanize
from datalad.utils import is_interactive

from logging import getLogger
lgr = getLogger('datalad.api.ls')


class Ls(Interface):
    """List summary information about URLs and dataset(s)

    ATM only s3:// URLs and datasets are supported

    Examples
    --------

      $ datalad ls s3://openfmri/tarballs/ds202  # to list S3 bucket
      $ datalad ls                               # to list current dataset
    """

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
        return self.repo.get_committed_date()

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
            self._info = self.repo.repo_info()
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
            super(self.__class__, self).date

    @property
    def size(self):
        """Size of the node computed based on its type"""
        type_ = self.type_
        sizes = {'total': 0.0, 'ondisk': 0.0, 'git': 0.0, 'annex': 0.0, 'annex_worktree': 0.0}

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
        print(ds_str)


def machinesize(humansize):
    """convert human-size string to machine-size"""
    try:
        size_str, size_unit = humansize.split(" ")
    except AttributeError:
        return float(humansize)
    unit_converter = {'Byte': 0, 'Bytes': 0, 'kB': 1, 'MB': 2, 'GB': 3, 'TB': 4, 'PB': 5}
    machinesize = float(size_str) * (1000 ** unit_converter[size_unit])
    return machinesize


def leaf_name(path):
    """takes a relative or absolute path and returns name of node at that location"""
    head, tail = split(abspath(path))
    return tail or basename(head)


def ignored(path, only_hidden=False):
    """if path is in the ignorelist return True

    ignore list includes hidden files and git or annex maintained folders
    when only_hidden set, only ignores hidden files and folders not git or annex maintained folders
    """
    if isdir(opj(path, ".git")) and not only_hidden:
        return True
    return '.' == leaf_name(path)[0] or leaf_name(path) == 'index.html'


def metadata_locator(fs_metadata=None, path=None, ds_path=None, metadata_path=None):
    """path to metadata file of node associated with the fs_metadata dictionary

    Parameters
    ----------
    fs_metadata: dict
      Metadata json of a node
    path: str
      Path to directory of metadata to be rendered
    ds_path: str
      Path to dataset root
    metadata_path: str
      Path to metadata root. Calculated relative to ds_path

    Returns
    -------
    str
      path to metadata of current node
    """

    # use implicit paths unless paths explicitly specified
    # Note: usage of ds_path as if it was the Repo's path. Therefore use
    # realpath, since we switched to have symlinks resolved in repos but not in
    # datasets
    ds_path = realpath(ds_path) if ds_path else fs_metadata['repo']
    path = path or fs_metadata['path']
    metadata_path = metadata_path or '.git/datalad/metadata'
    # directory metadata directory tree location
    metadata_dir = opj(ds_path, metadata_path)
    # relative path of current directory wrt dataset root
    dir_path = relpath(path, ds_path) if isabs(path) else path
    # normalize to / -- TODO, switch to '.' which is now actually the name since path is relative in web meta?
    if dir_path in ('.', None, ''):
        dir_path = '/'
    # create md5 hash of current directory's relative path
    metadata_hash = hashlib.md5(dir_path.encode('utf-8')).hexdigest()
    # construct final path to metadata file
    metadata_file = opj(metadata_dir, metadata_hash)

    return metadata_file


def fs_extract(nodepath, repo, basepath='/'):
    """extract required info of nodepath with its associated parent repository and returns it as a dictionary

    Parameters
    ----------
    nodepath : str
        Full path to the location we are exploring (must be a directory within
        `repo`
    repo : GitRepo
        Is the repository nodepath belongs to
    """
    # Create FsModel from filesystem nodepath and its associated parent repository
    node = FsModel(nodepath, repo)
    pretty_size = {stype: humanize.naturalsize(svalue) for stype, svalue in node.size.items()}
    pretty_date = time.strftime(u"%Y-%m-%d %H:%M:%S", time.localtime(node.date))
    name = leaf_name(node._path) if leaf_name(node._path) != "" else leaf_name(node.repo.path)
    rec = {
        "name": name, "path": relpath(node._path, basepath),
        "type": node.type_, "size": pretty_size, "date": pretty_date,
    }
    # if there is meta-data for the dataset (done by aggregate-metadata)
    # we include it
    metadata_path = opj(nodepath, METADATA_DIR, METADATA_FILENAME)
    if exists(metadata_path):
        # might need flattening!  TODO: flatten when aggregating?  why wasn't done?
        metadata = js.load(open(metadata_path))
        # might be too heavy to carry around, so will do basic flattening manually
        # and in a basic fashion
        # import jsonld
        metadata_reduced = metadata[0]
        for m in metadata[1:]:
            metadata_reduced.update(m)
        # but verify that they all had the same id
        if metadata:
            metaid = metadata[0]['@id']
            assert all(m['@id'] == metaid for m in metadata)
        rec["metadata"] = metadata_reduced
    return rec


def fs_render(fs_metadata, json=None, **kwargs):
    """takes node to render and based on json option passed renders to file, stdout or deletes json at root

    Parameters
    ----------
    fs_metadata: dict
      Metadata json to be rendered
    json: str ('file', 'display', 'delete')
      Render to file, stdout or delete json
    """

    metadata_file = metadata_locator(fs_metadata, **kwargs)

    if json == 'file':
        # create metadata_root directory if it doesn't exist
        metadata_dir = dirname(metadata_file)
        if not exists(metadata_dir):
            makedirs(metadata_dir)
        # write directory metadata to json
        with open(metadata_file, 'w') as f:
            js.dump(fs_metadata, f)

    # else if json flag set to delete, remove .dir.json of current directory
    elif json == 'delete' and exists(metadata_file):
        remove(metadata_file)

    # else dump json to stdout
    elif json == 'display':
        print(js.dumps(fs_metadata) + '\n')


def fs_traverse(path, repo, parent=None, render=True, recursive=False, json=None, basepath=None):
    """Traverse path through its nodes and returns a dictionary of relevant attributes attached to each node

    Parameters
    ----------
    path: str
      Path to the directory to be traversed
    repo: AnnexRepo or GitRepo
      Repo object the directory belongs too
    parent: dict
      Extracted info about parent directory
    recursive: bool
      Recurse into subdirectories (note that subdatasets are not traversed)
    render: bool
       To render from within function or not. Set to false if results to be manipulated before final render

    Returns
    -------
    list of dict
      extracts and returns a (recursive) list of directory info at path
      does not traverse into annex, git or hidden directories
    """
    fs = fs_extract(path, repo, basepath=basepath or path)
    if isdir(path):                     # if node is a directory
        children = [fs.copy()]          # store its info in its children dict too  (Yarik is not sure why, but I guess for .?)
        # ATM seems some pieces still rely on having this duplication, so left as is
        # TODO: strip away
        for node in listdir(path):
            nodepath = opj(path, node)

            # TODO:  it might be a subdir which is non-initialized submodule!
            # if not ignored, append child node info to current nodes dictionary
            if not ignored(nodepath):
                # if recursive, create info dictionary (within) each child node too
                if recursive:
                    subdir = fs_traverse(nodepath,
                                         repo,
                                         parent=None,  # children[0],
                                         recursive=recursive,
                                         json=json,
                                         basepath=basepath or path)
                    subdir.pop('nodes', None)
                else:
                    # read child metadata from its metadata file if it exists
                    subdir_json = metadata_locator(path=node, ds_path=basepath or path)
                    if exists(subdir_json):
                        with open(subdir_json) as data_file:
                            subdir = js.load(data_file)
                            subdir.pop('nodes', None)
                    # else extract whatever information you can about the child
                    else:
                        # Yarik: this one is way too lean...
                        subdir = fs_extract(nodepath,
                                            repo,
                                            basepath=basepath or path)
                # append child metadata to list
                children.extend([subdir])

        # sum sizes of all 1st level children
        children_size = {}
        for node in children[1:]:
            for size_type, child_size in node['size'].items():
                children_size[size_type] = children_size.get(size_type, 0) + machinesize(child_size)

        # update current node sizes to the humanized aggregate children size
        fs['size'] = children[0]['size'] = \
            {size_type: humanize.naturalsize(child_size)
             for size_type, child_size in children_size.items()}

        children[0]['name'] = '.'       # replace current node name with '.' to emulate unix syntax
        if parent:
            parent['name'] = '..'       # replace parent node name with '..' to emulate unix syntax
            children.insert(1, parent)  # insert parent info after current node info in children dict

        fs['nodes'] = children          # add children info to main fs dictionary
        if render:                      # render directory node at location(path)
            fs_render(fs, json=json, ds_path=basepath or path)
            lgr.info('Directory: %s' % path)

    return fs


def ds_traverse(rootds, parent=None, json=None, recursive=False, all_=False,
                long_=False):
    """Hierarchical dataset traverser

    Parameters
    ----------
    rootds: Dataset
      Root dataset to be traversed
    parent: Dataset
      Parent dataset of the current rootds
    recursive: bool
       Recurse into subdirectories of the current dataset
    all_: bool
       Recurse into subdatasets of the root dataset

    Returns
    -------
    list of dict
      extracts and returns a (recursive) list of dataset(s) info at path
    """
    # extract parent info to pass to traverser
    fsparent = fs_extract(parent.path, parent.repo, basepath=rootds.path) if parent else None

    # (recursively) traverse file tree of current dataset
    fs = fs_traverse(rootds.path, rootds.repo,
                     render=False, parent=fsparent, recursive=all_,
                     json=json)
    size_list = [fs['size']]

    # (recursively) traverse each subdataset
    children = []
    # yoh: was in return results branch returning full datasets:
    # for subds in rootds.subdatasets(result_xfm='datasets'):
    # but since rpath is needed/used, decided to return relpaths
    for subds_rpath in rootds.subdatasets(result_xfm='relpaths'):

        subds_path = opj(rootds.path, subds_rpath)
        subds = Dataset(subds_path)
        subds_json = metadata_locator(path='.', ds_path=subds_path)

        def handle_not_installed():
            # for now just traverse as fs
            lgr.warning("%s is either not installed or lacks meta-data", subds)
            subfs = fs_extract(subds_path, rootds, basepath=rootds.path)
            # but add a custom type that it is a not installed subds
            subfs['type'] = 'uninitialized'
            # we need to kick it out from 'children'
            # TODO:  this is inefficient and cruel -- "ignored" should be made
            # smarted to ignore submodules for the repo
            if fs['nodes']:
                fs['nodes'] = [c for c in fs['nodes'] if c['path'] != subds_rpath]
            return subfs

        if not subds.is_installed():
            subfs = handle_not_installed()
        elif recursive:
            subfs = ds_traverse(subds,
                                json=json,
                                recursive=recursive,
                                all_=all_,
                                parent=rootds)
            subfs.pop('nodes', None)
            size_list.append(subfs['size'])
        # else just pick the data from metadata_file of each subdataset
        else:
            lgr.info(subds.path)
            if exists(subds_json):
                with open(subds_json) as data_file:
                    subfs = js.load(data_file)
                    subfs.pop('nodes', None)    # remove children
                    subfs['path'] = subds_rpath # reassign the path
                    size_list.append(subfs['size'])
            else:
                # the same drill as if not installed
                lgr.warning("%s is installed but no meta-data yet", subds)
                subfs = handle_not_installed()

        children.extend([subfs])

    # sum sizes of all 1st level children dataset
    children_size = {}
    for subdataset_size in size_list:
        for size_type, subds_size in subdataset_size.items():
            children_size[size_type] = children_size.get(size_type, 0) + machinesize(subds_size)

    # update current dataset sizes to the humanized aggregate subdataset sizes
    fs['size'] = {size_type: humanize.naturalsize(size)
                  for size_type, size in children_size.items()}
    fs['nodes'][0]['size'] = fs['size']  # update self's updated size in nodes sublist too!

    # add dataset specific entries to its dict
    rootds_model = GitModel(rootds.repo)
    fs['tags'] = rootds_model.describe
    fs['branch'] = rootds_model.branch
    index_file = opj(rootds.path, '.git', 'index')
    fs['index-mtime'] = time.strftime(
        u"%Y-%m-%d %H:%M:%S",
        time.localtime(getmtime(index_file))) if exists(index_file) else ''

    # append children datasets info to current dataset
    fs['nodes'].extend(children)

    # render current dataset
    lgr.info('Dataset: %s' % rootds.path)
    fs_render(fs, json=json, ds_path=rootds.path)
    return fs


def _ls_json(loc, fast=False, **kwargs):
    # hierarchically traverse file tree of (sub-)dataset(s) under path passed(loc)
    return ds_traverse(Dataset(loc), parent=None, **kwargs)


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
    for acc in ACCESS_METHODS:
        try:
            prefix_all_versions = list(acc(prefix, **kwargs))
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
            if not (e.is_latest or all_):
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
            if long_:
                ui.message("ver:%-32s  acl:%s  %s [%s]%s" % (e.version_id, acl, url, urlok, content))
            else:
                ui.message('')
        else:
            ui.message(base_msg + " " + str(type(e)).split('.')[-1].rstrip("\"'>"))
    return results
