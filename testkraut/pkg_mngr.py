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

import logging
lgr = logging.getLogger(__name__)
import os

class PkgManager(object):
    """Simple abstraction layer to query local package managers"""
    def __init__(self):
        self._mode = None
        self._native_pkg_cache = None
        from .utils import run_command
        try:
            import apt
            self._native_pkg_cache = apt.Cache()
            self._mode = 'deb'
        except ImportError:
            # it could still be debian, but without python-apt
            ret = run_command('dpkg --version')
            if ret['retval'] == 0:
                self._mode = 'deb'
                lgr.warning("Running on Debian platform but no python-apt "
                            "package found -- only limited information is "
                            "available.")
        if self._mode is None:
            # maybe RPM?
            ret = run_command('rpm --version')
            if ret['retval'] == 0:
                self._mode = 'rpm'

    def get_pkg_name(self, filename):
        """Return the name of a package providing a file (if any).

        Returns None if no package provides this file, or no package manager is
        available.
        """
        if os.path.exists(filename):
            # if the file actually exists try resolving symlinks
            filename = os.path.realpath(filename)
        if self._mode == 'deb':
            return _get_debian_pkgname(filename)
        elif self._mode == 'rpm':
            from .utils import run_command
            ret = run_command("rpm --queryformat '%%{NAME}\n' -qf %s" % filename)
            if not ret['retval'] == 0:
                return None
            return ret['stdout'][0]
        return None

    def get_pkg_info(self, pkgname):
        """Returns a dict with information on a given package."""
        info = dict(name=pkgname)
        if self._mode == 'deb':
            return self._get_debian_pkginfo(pkgname, info)
        elif self._mode == 'rpm':
            from .utils import run_command
            ret = run_command('rpm --qf \'\{"version":"%%{EVR}", "sha1sum":"%%{SHA1HEADER}", "vendor":"%%{VENDOR}", "arch":"%%{ARCH}"\}\n\' -q %s' % pkgname)
            if ret['retval'] == 0:
                info.update(eval('\n'.join(ret['stdout'])))
        return info

    def _get_debian_pkginfo(self, pkgname, debinfo):
        apt = self._native_pkg_cache
        if not apt is None:
            pkg = apt[pkgname].installed
            if pkg is None:
                # no such package installed
                return debinfo
            debinfo['version'] = pkg.version
            debinfo['sha1sum'] = pkg.sha1
            debinfo['arch'] = pkg.architecture
            origin = pkg.origins[0]
            debinfo['vendor'] = origin.origin
        return debinfo

    def get_platform_name(self):
        """Returns the local package manager type.

        For example, 'deb', 'rpm', or None if no supported package manager
        was found.
        """
        return self._mode


def _get_debian_pkgname(filename):
    from .utils import run_command
    # provided by a Debian package?
    pkgname = None
    try:
        ret = run_command('dpkg -S %s' % filename)
    except OSError:
        return None
    if not ret['retval'] == 0:
        return None
    for line in ret['stdout']:
        lspl = line.split(':')
        if lspl[0].count(' '):
            continue
        pkgname = lspl[0]
        break
    return pkgname
