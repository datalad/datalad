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
import time

from os.path import basename

from collections import OrderedDict
from collections import defaultdict

from logging import getLogger
lgr = getLogger('datalad.support.versions')


def get_versions(vfpath_statuses, regex, overlay=True,
                 unversioned=None, default=None, always_versioned=None,
                 versioneer=None):
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
      to generate unversioned path (fpath)
    overlay: bool, optional
      Assume overlayed structure, so if a file misses an entry for some version,
      it is ok
    unversioned: ('fail', 'default'), optional
      What to do if detected both versioned and unversioned file.
      If `default` then specified `default` argument can be used as a
      format string for time.strftime which by default we provide
      '%Y%m%d' (corresponds to `YYYYMMDD`) from mtime of the provided status.
      If no '%' found in `default`, its value is used as is and no status is needed.
      If `unversioned` is None and `default` is specified -- assume 'default', and
      'fail' otherwise.
    always_versioned: str, optional
      Regular expression to force versioning of file names matching the regex.
    default: str, optional
      Default version to use in case of unversioned is 'default'
    versioneer: callable, optional
      To convert parsed out version, provided the unversioned filename,
      version and status

    Returns
    -------
    OrderedDict
      version -> {fpath: (vfpath, status)} or {fpath: vfpath}
      Last one if no statuses were provided

    """
    if unversioned is None:
        unversioned = 'fail' if default is None else 'default'
    if unversioned == 'default' and default is None:
        default = '0.0.%Y%m%d'

    if not overlay:
        raise NotImplementedError(overlay)
        # we should add a check that if there is a gap in versions for some file
        # then we must ... puke?

    # collect all versioned files for now in non-ordered dict
    # vfpaths = {}  # file -> [versions]
    all_versions = defaultdict(dict)  # version -> {fpath: (vfpath, status)}
    nunversioned = nversioned = 0
    statuses = {}
    for entry in vfpath_statuses:
        if isinstance(entry, tuple):
            vfpath, status = entry
        else:
            vfpath, status = entry, None
        statuses[vfpath] = status  # might come handy later
        # reapply regex to extract version
        res = re.search(regex, vfpath)
        if not res:
            # unversioned
            nunversioned += 1
            fpath = vfpath
            if always_versioned and re.match(always_versioned, basename(vfpath)):
                version = _get_default_version(entry, default, status)
            else:
                version = None
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
                version = versioneer(fpath, version, status)

        # 1 more version for the file, must not be there already!
        assert(fpath not in all_versions[version])
        all_versions[version][fpath] = entry

    lgr.log(5, "Found %d versioned files of %d versions: %s",
            nversioned,
            len(all_versions),
            all_versions if nversioned + nunversioned < 100 else "too many to list")

    if None in all_versions:
        # check if for each one of them there is no unversioned one
        # we will be augmenting all_versions, thus go through those keys we have so far
        for version in list(all_versions):
            fpaths = all_versions[version]
            if version is None:
                continue
            for fpath in fpaths:
                if fpath in all_versions[None]:
                    # So we had versioned AND unversioned
                    if unversioned == 'fail':
                        raise ValueError(
                            "There is an unversioned file %r whenever also following "
                            "version for it was found: %s" % (fpath, version))
                    elif unversioned == 'default':
                        version = _get_default_version(entry, default, status)
                        all_versions[version][fpath] = all_versions[None].pop(fpath)
                    else:
                        raise ValueError("Do not know how to handle %r" % (unversioned,))
        if not all_versions[None]:
            # may be no unversioned left
            all_versions.pop(None)

    # sort all the versions and place into an ordered dictionary, but strip None first
    had_None = None in all_versions
    versions_sorted = list(map(str, sorted((LooseVersion(v) for v in all_versions if v is not None))))
    if had_None:
        versions_sorted = [None] + versions_sorted

    return OrderedDict(((v, all_versions[v]) for v in versions_sorted))


def _get_default_version(entry, default, status):
    if '%' in default:  # so we seek strftime formatting
        if status is None:
            raise ValueError(
                "No status was provided within %r entry. "
                "No mtime could be figured out for this unversioned file" % entry)
        return time.strftime(default, time.localtime(status.mtime))
    else:  # just the default
        return default
