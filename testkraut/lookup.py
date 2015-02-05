# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj
import re
import shutil
from datetime import datetime
from uuid import uuid1 as uuid
from . import utils
from .utils import run_command, get_shlibdeps, which, sha1sum, \
        get_script_interpreter, describe_system, get_test_library_paths, \
        get_filecache_dir, download_file
from .pkg_mngr import PkgManager
from .spec import SPEC
import testkraut
from testkraut import cfg
import logging
lgr = logging.getLogger(__name__)

def check_file_hash(filespec, filepath):
    """Check the hash of a file given a file SPEC

    If not target hash is present in the file SPEC ``None`` is returned.
    Otherwise a boolean return value indicated whether the hash matches.
    """
    for hashtype in ('md5sum', 'sha1sum'):
        if hashtype in filespec:
            targethash = filespec[hashtype]
            hasher = getattr(utils, hashtype)
            observedhash = hasher(filepath)
            if targethash != observedhash:
                lgr.debug("hash for '%s' does not match ('%s' != '%s')"
                          % (filepath, observedhash, targethash))
                return False
            else:
                lgr.debug("hash for '%s' matches ('%s')"
                          % (filepath, observedhash))
                return True
    lgr.debug("no hash for '%s' found" % filepath)
    return None

def locate_file_in_cache(filespec, cache):
    """Very simple cache lookup -- to be replaced with proper cache object"""
    if filespec is None:
        filespec = dict()
    if not 'sha1sum' in filespec:
        # nothing we can do
        lgr.debug("cannot lookup file in cache without sha1sum")
        return None
    sha1 = filespec['sha1sum']
    cand_filename = opj(cache, sha1)
    if os.path.isfile(cand_filename):
        lgr.debug("found file with sha1sum %s in cache" % sha1)
        return cand_filename
    lgr.debug("hash '%s' not present in cache '%s'"
              % (sha1, cache))
    return None

def place_file_into_dir(filespec, dest_dir, search_dirs=None, cache=None,
                        force_overwrite=True, symlink_to_cache=True):
    """Search for a file given a SPEC and place it into a destination directory

    Parameters
    ----------
    filespec : SPEC dict
      Dictionary with information on the file, keys could be, e.g., 'value',
      'type', or 'sha1sum'.
    dest_dir : path
      Path of the destination/target directory
    search_dirs : None or sequence
      If not None, a sequence of additional local directories to be searched for
      the desired file (tetskraut configuration might provide more locations
      that will also be searched afterwards)
    cache : None or path
      If not None, a path to a file cache directory where the desired file is
      searched by its sha1sum (if present in the SPEC)
    """
    # TODO refactor from simple cachedir to cache object that could also obtain
    # a file from remote locations

    # sanity
    if not 'type' in filespec or filespec['type'] != 'file':
        raise ValueError("expected SPEC is not a file SPEC, got : '%s'"
                         % filespec)
    # have a default cache
    if cache is None:
        cache = get_filecache_dir()
    if not os.path.exists(cache):
        os.makedirs(cache)
    # search path
    if search_dirs is None:
        search_dirs = []
    search_dirs += cfg.get('data sources', 'local dirs', default='').split()

    fname = filespec['value']
    # where the file needs to end up in the testbed
    dest_fname = opj(dest_dir, fname)
    # this will be the discovered file path
    fpath = None
    # first try the cache
    fpath = locate_file_in_cache(filespec, cache)
    # do a local search
    if fpath is None and len(search_dirs):
        lgr.debug("cache lookup for '%s' unsuccessful, trying local search"
                  % fname)
        # do a two-pass scan: first try locating the file by name to avoid
        # sha1-summing all files
        for search_dir in search_dirs:
            for root, dirnames, filenames in os.walk(search_dir):
                cand_path = opj(root, fname)
                if not os.path.isfile(cand_path):
                    lgr.debug("could not find file '%s' at '%s'"
                              % (fname, cand_path))
                    continue
                hashmatch = check_file_hash(filespec, cand_path)
                if hashmatch in (True, None):
                    lgr.debug("found matching file '%s' at '%s'"
                              % (fname, cand_path))
                    # run with the file if there is no hash or it matches
                    fpath = cand_path
                    break
            if not fpath is None:
                break
        if fpath is None and ('sha1sum' in filespec or 'md5sum' in filespec):
            lgr.debug("could not find file '%s' by its name, doing hash lookup"
                      % fname)
            # 2nd pass if we have a hash try locating by hash
            for search_dir in search_dirs:
                for root, dirnames, filenames in os.walk(search_dir):
                    for cand_name in filenames:
                        cand_path = opj(root, cand_name)
                        if check_file_hash(filespec, cand_path) is True:
                            lgr.debug("found matching file '%s' at '%s'"
                                      % (fname, cand_path))
                            fpath = cand_path
                            break
                    if not fpath is None:
                        break
                if not fpath is None:
                    break
        if not fpath is None and ('md5sum' in filespec or 'sha1sum' in filespec):
            # place in cache -- but only if any hash is given in the file spec
            # if no hash is given, this file is volatile and it makes no sense
            # to cache it
            if not 'sha1sum' in filespec:
                sha1 = sha1sum(fpath)
            else:
                sha1 = filespec['sha1sum']
            dst_path = opj(cache, sha1)
            if os.path.exists(dst_path) or os.path.lexists(dst_path):
                os.remove(dst_path)
                lgr.debug("removing existing cache entry '%s'" % dst_path)
            if symlink_to_cache:
                os.symlink(fpath, dst_path)
                lgr.debug("symlink to cache '%s'->'%s'" % (fpath, dst_path))
            elif hasattr(os, 'link'):
                # be nice and try hard-linking
                try:
                    os.link(fpath, dst_path)
                    lgr.debug("hardlink to cache '%s'->'%s'" % (fpath, dst_path))
                except OSError:
                    # silently fail if linking doesn't work (e.g.
                    # cross-device link ... will recover later
                    shutil.copy(fpath, dst_path)
                    lgr.debug("copy to cache '%s'->'%s'" % (fpath, dst_path))
            else:
                shutil.copy(fpath, dst_path)
                lgr.debug("copy to cache '%s'->'%s'" % (fpath, dst_path))
    # trying external data sources
    if fpath is None and 'url' in filespec:
        # url is given
        fpath = download_file(filespec['url'], dest_fname)
    if fpath is None and 'sha1sum' in filespec:
        # lookup in any configured hash store
        hashpots = cfg.get('data sources', 'hash stores').split()
        sha1 = filespec['sha1sum']
        lgr.debug("local search '%s' unsuccessful, trying hash stores"
                  % fname)
        dst_path = opj(cache, sha1)
        for hp in hashpots:
            fpath = download_file('%s%s' % (hp, sha1), dst_path)
            if not fpath is None:
                break
    if fpath is None:
        # out of ideas
        raise LookupError("cannot find file matching spec %s" % filespec)
    # get the file into the dest_dir
    if not fpath == dest_fname \
       and (force_overwrite or not os.path.isfile(dest_fname)):
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        shutil.copy(fpath, dest_fname)
    else:
        lgr.debug("skip copying already present file '%s'" % fname)


def prepare_local_testbed(spec, dst, search_dirs, cache=None,
                          force_overwrite=True):
    inspecs = spec.get('inputs', {})
    # locate and copy test input into testbed
    for inspec_id in inspecs:
        inspec = inspecs[inspec_id]
        type_ = inspec['type']
        if type_ == 'file':
            place_file_into_dir(inspec, dst,
                                search_dirs=search_dirs, cache=cache,
                                force_overwrite=force_overwrite)
        else:
            raise ValueError("unknown input spec type '%s'" % type_)
