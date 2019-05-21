# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper to create listing for web UI such as on http://datasets.datalad.org
"""
__docformat__ = 'restructuredtext'

import hashlib
import numbers
import humanize
import json as js
import time
from genericpath import isdir, exists, getmtime
from os import makedirs, remove, listdir
from os.path import split, abspath, basename, join as opj, realpath, relpath, \
    isabs, dirname

from datalad.consts import OLDMETADATA_DIR, OLDMETADATA_FILENAME
from datalad.distribution.dataset import Dataset
from datalad.interface.ls import FsModel, lgr, GitModel
from datalad.support.network import is_datalad_compat_ri
from datalad.utils import safe_print, with_pathsep

# A string to use to depict unknown size of the annexed dataset, e.g.
# whenever all the keys are "relaxed" urls
UNKNOWN_SIZE = "?"


def machinesize(humansize):
    """convert human-size string to machine-size"""
    if humansize == UNKNOWN_SIZE:
        return 0
    try:
        size_str, size_unit = humansize.split(" ")
    except AttributeError:
        return float(humansize)
    unit_converter = {
        'Byte': 0, 'Bytes': 0, 'kB': 1, 'MB': 2, 'GB': 3, 'TB': 4, 'PB': 5
    }
    machinesize = float(size_str) * (1000 ** unit_converter[size_unit])
    return machinesize


def leaf_name(path):
    """takes a relative or absolute path and returns name of node at that location"""
    head, tail = split(abspath(path))
    return tail or basename(head)


def ignored(path, only_hidden=False):
    """if path is in the ignorelist return True

    ignore list includes hidden files and git or annex maintained folders
    when only_hidden set, only ignores hidden files and folders not git or annex
     maintained folders
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
        `repo`)
    repo : GitRepo
        Is the repository nodepath belongs to
    """
    # Create FsModel from filesystem nodepath and its associated parent repository
    node = FsModel(nodepath, repo)
    pretty_size = {
        stype: humanize.naturalsize(svalue)
            if isinstance(svalue, numbers.Number) else UNKNOWN_SIZE
        for stype, svalue in node.size.items()
    }
    pretty_date = time.strftime(u"%Y-%m-%d %H:%M:%S", time.localtime(node.date))
    name = leaf_name(node._path) \
        if leaf_name(node._path) != "" \
        else leaf_name(node.repo.path)
    rec = {
        "name": name,
        "path": relpath(node._path, basepath),
        "type": node.type_,
        "size": pretty_size,
        "date": pretty_date,
    }
    # if there is meta-data for the dataset (done by aggregate-metadata)
    # we include it
    metadata_path = opj(nodepath, OLDMETADATA_DIR, OLDMETADATA_FILENAME)
    if exists(metadata_path):
        # might need flattening!  TODO: flatten when aggregating?  why wasn't done?
        with open(metadata_path) as t:
            metadata = js.load(t)
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
    """render node based on json option passed renders to file, stdout or deletes json at root

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
        safe_print(js.dumps(fs_metadata) + '\n')


def fs_traverse(path, repo, parent=None,
                subdatasets=None,
                render=True,
                recurse_datasets=False,
                recurse_directories=False,
                json=None, basepath=None):
    """Traverse path through its nodes and returns a dictionary of relevant
    attributes attached to each node

    Parameters
    ----------
    path: str
      Path to the directory to be traversed
    repo: AnnexRepo or GitRepo
      Repo object the directory belongs too
    parent: dict
      Extracted info about parent directory
    recurse_directories: bool
      Recurse into subdirectories (note that subdatasets are not traversed)
    render: bool
       To render from within function or not. Set to false if results to be
       manipulated before final render

    Returns
    -------
    list of dict
      extracts and returns a (recursive) list of directory info at path
      does not traverse into annex, git or hidden directories
    """
    subdatasets = subdatasets or []
    fs = fs_extract(path, repo, basepath=basepath or path)
    dataset = Dataset(repo.path)
    submodules = {sm.path: sm
                  for sm in repo.get_submodules()}
    # TODO:  some submodules might not even have a local empty directory
    # (git doesn't care about those), so us relying on listdir here and
    # for _traverse_handle_subds might not work out.
    # E.g. create-sibling --ui true ... --existing=reconfigure
    #  causes removal of those empty ones on the remote end
    if isdir(path):                     # if node is a directory
        children = [fs.copy()]          # store its info in its children dict too  (Yarik is not sure why, but I guess for .?)
        # ATM seems some pieces still rely on having this duplication, so left as is
        # TODO: strip away
        for node in listdir(path):
            nodepath = opj(path, node)

            # Might contain subdatasets, so we should analyze and prepare entries
            # to pass down... in theory we could just pass full paths may be? strip
            node_subdatasets = []
            is_subdataset = False
            if isdir(nodepath):
                node_sep = with_pathsep(node)
                for subds in subdatasets:
                    if subds == node:
                        # it is the subdataset
                        is_subdataset = True
                    else:
                        # use path_is_subdir
                        if subds.startswith(node_sep):
                            node_subdatasets += [subds[len(node_sep):]]

            # TODO:  it might be a subdir which is non-initialized submodule!
            # if not ignored, append child node info to current nodes dictionary
            if is_subdataset:
                # repo.path is real, so we are doomed (for now at least)
                # to resolve nodepath as well to get relpath for it
                node_relpath = relpath(realpath(nodepath), repo.path)
                subds = _traverse_handle_subds(
                    node_relpath,
                    dataset,
                    recurse_datasets=recurse_datasets,
                    recurse_directories=recurse_directories,
                    json=json
                )
                # Enhance it with external url if available
                submod_url = submodules[node_relpath].url
                if submod_url and is_datalad_compat_ri(submod_url):
                    subds['url'] = submod_url
                children.append(subds)
            elif not ignored(nodepath):
                # if recursive, create info dictionary (within) each child node too
                if recurse_directories:
                    subdir = fs_traverse(nodepath,
                                         repo,
                                         subdatasets=node_subdatasets,
                                         parent=None,  # children[0],
                                         recurse_datasets=recurse_datasets,
                                         recurse_directories=recurse_directories,
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


def ds_traverse(rootds, parent=None, json=None,
                recurse_datasets=False, recurse_directories=False,
                long_=False):
    """Hierarchical dataset traverser

    Parameters
    ----------
    rootds: Dataset
      Root dataset to be traversed
    parent: Dataset
      Parent dataset of the current rootds
    recurse_datasets: bool
      Recurse into subdatasets of the root dataset
    recurse_directories: bool
      Recurse into subdirectories of the current dataset
      In both of above cases, if False, they will not be explicitly
      recursed but data would be loaded from their meta-data files

    Returns
    -------
    list of dict
      extracts and returns a (recursive) list of dataset(s) info at path
    """
    # extract parent info to pass to traverser
    fsparent = fs_extract(parent.path, parent.repo, basepath=rootds.path) \
        if parent else None

    # (recursively) traverse file tree of current dataset
    fs = fs_traverse(
        rootds.path, rootds.repo,
        subdatasets=list(rootds.subdatasets(result_xfm='relpaths')),
        render=False,
        parent=fsparent,
        # XXX note that here I kinda flipped the notions!
        recurse_datasets=recurse_datasets,
        recurse_directories=recurse_directories,
        json=json
    )

    # BUT if we are recurse_datasets but not recurse_directories
    #     we need to handle those subdatasets then somehow since
    #     otherwise we might not even get to them?!

    fs['nodes'][0]['size'] = fs['size']  # update self's updated size in nodes sublist too!

    # add dataset specific entries to its dict
    rootds_model = GitModel(rootds.repo)
    fs['tags'] = rootds_model.describe
    fs['branch'] = rootds_model.branch
    index_file = opj(rootds.path, '.git', 'index')
    fs['index-mtime'] = time.strftime(
        u"%Y-%m-%d %H:%M:%S",
        time.localtime(getmtime(index_file))) if exists(index_file) else ''

    # render current dataset
    lgr.info('Dataset: %s' % rootds.path)
    fs_render(fs, json=json, ds_path=rootds.path)
    return fs


def _traverse_handle_subds(
        subds_rpath, rootds,
        recurse_datasets, recurse_directories, json):
    """A helper to deal with the subdataset node - recurse or just pick up
    may be alrady collected in it web meta
    """
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
        #if fs['nodes']:
        #    fs['nodes'] = [c for c in fs['nodes'] if c['path'] != subds_rpath]
        return subfs

    if not subds.is_installed():
        subfs = handle_not_installed()
    elif recurse_datasets:
        subfs = ds_traverse(subds,
                            json=json,
                            recurse_datasets=recurse_datasets,
                            recurse_directories=recurse_directories,
                            parent=rootds)
        subfs.pop('nodes', None)
        #size_list.append(subfs['size'])
    # else just pick the data from metadata_file of each subdataset
    else:
        subfs = None
        lgr.info(subds.path)
        if exists(subds_json):
            with open(subds_json) as data_file:
                subfs = js.load(data_file)
                subfs.pop('nodes', None)  # remove children
                subfs['path'] = subds_rpath  # reassign the path
                #size_list.append(subfs['size'])
        else:
            # the same drill as if not installed
            lgr.warning("%s is installed but no meta-data yet", subds)
            subfs = handle_not_installed()
    # add URL field

    return subfs


def _ls_json(loc, fast=False, **kwargs):
    # hierarchically traverse file tree of (sub-)dataset(s) under path
    # passed(loc)
    recurse_datasets = kwargs.pop('recursive', False)
    recurse_directories = kwargs.pop('all_', False)
    return ds_traverse(
        Dataset(loc), parent=None,
        recurse_directories=recurse_directories,
        recurse_datasets=recurse_datasets,
        **kwargs)