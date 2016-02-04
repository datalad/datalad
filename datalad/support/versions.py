# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Primarily to support crawler's operations on versioned files
"""

import re
from distutils.version import LooseVersion

import os
from os import unlink
from os.path import splitext, dirname, basename, curdir
from os.path import lexists
from os.path import join as opj

from collections import OrderedDict
from six import iteritems
from ..utils import updated
from ..utils import find_files
from ..dochelpers import exc_str
from ..downloaders.base import DownloadError
from ..downloaders.providers import Providers

from logging import getLogger
lgr = getLogger('datalad.support.versions')


def get_versions(vfpath_statuses, regex, overlay=True, unversioned='fail', versioneer=None):
    """Return an ordered dict of versions with entries being vfpath_statuses

    ATM doesn't care about statuses but it might in the future so we could
    get more sophisticated separation into versions, e.g. based on batches of
    changes in S3 based on mtime

    Parameters
    ----------
    vfpath_statuses: iterable of filepaths or (filepath, status) pairs
    regex: str
      Regular expression to extract version.  Group 'version' should be defined
      if more than a single group present. If no groups defined at all, entire
      match considered to be a version.  Matched entry is stripped from the filename
      to generated unversioned path (fpath)
    overlay: bool, optional
      Assume overlayed structure, so if a file misses an entry for some version,
      it is ok
    uversioned: ('fail'), optional
      What to do if detected both versioned and unversioned file
    versioneer: callable, optional
      To convert parsed out version

    Returns
    -------
    OrderedDict
      version -> {fpath: (vfpath, status)} or {fpath: vfpath}
      Last one if no statuses were provided

    """
    if not overlay:
        raise NotImplementedError(overlay)
        # we should add a check that if there is a gap in versions for some file
        # then we must ... puke?


    # collect all versioned files for now in non-ordered dict
    # vfpaths = {}  # file -> [versions]
    all_versions = {}  # version -> {fpath: (vfpath, status)}
    nunversioned = nversioned = 0
    for entry in vfpath_statuses:
        if isinstance(entry, tuple):
            vfpath, status = entry
        else:
            vfpath, status = entry, None
        # reapply regex to extract version
        res = re.search(regex, vfpath)
        if not res:
            # unversioned
            nunversioned += 1
            version = None
            fpath = vfpath
        else:
            nversioned += 1
            fpath = vfpath[:res.start()] + vfpath[res.end():]  # unversioned one
            groups = res.groups()
            if groups:
                if len(groups) > 1:
                    if 'version' not in res.groupdict():
                        raise ValueError("Multiple groups found in regexp %r but no version group: %s"
                                         % (regex, groups))
                    version = res.groupdict().get('version')
                else:
                    version = groups[0]
            else:
                version = vfpath[res.start():res.end()]
            if versioneer:
                version = versioneer(version)
        if version not in all_versions:
            all_versions[version] = {}

        # 1 more version for the file, must not be there already!
        assert(fpath not in all_versions[version])
        all_versions[version][fpath] = entry

    lgr.log(5, "Found %d versioned files of %d versions: %s",
            nversioned,
            len(all_versions),
            all_versions if nversioned + nunversioned < 100 else "too many to list")

    # sort all the versions and place into an ordered dictionary
    had_None = None in all_versions
    versions_sorted = list(map(str, sorted((LooseVersion(v) for v in all_versions if v is not None))))
    if had_None:
        versions_sorted = [None] + versions_sorted

    versions = OrderedDict(((v, all_versions[v]) for v in versions_sorted))

    if unversioned == 'fail':
        if None in versions:
            # check if for each one of them there is no unversioned one
            for version, fpaths in iteritems(versions):
                if version is None:
                    continue
                for fpath in fpaths:
                    if fpath in versions[None]:
                        raise ValueError(
                            "There is an unversioned file %r whenever also following "
                            "version for it was found: %s" % (fpath, version))

    return versions


