# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to help maintain a registry of versions for external modules etc
"""
import re
import sys
import os.path as op
from os import linesep

from distutils.version import LooseVersion
from itertools import chain

from datalad.log import lgr
# import version helper from config to have only one implementation
# config needs this to avoid circular imports
from datalad.config import get_git_version as __get_git_version
from .exceptions import (
    CapturedException,
    CommandError,
)

__all__ = ['UnknownVersion', 'ExternalVersions', 'external_versions']


# To depict an unknown version, which can't be compared by mistake etc
class UnknownVersion:
    """For internal use
    """

    def __str__(self):
        return "UNKNOWN"

    def __cmp__(self, other):
        if other is self:
            return 0
        raise TypeError("UNKNOWN version is not comparable")


#
# Custom handlers
#
from datalad.cmd import (
    WitlessRunner,
    GitWitlessRunner,
    StdOutErrCapture,
)
from datalad.support.exceptions import (
    MissingExternalDependency,
    OutdatedExternalDependency,
)
_runner = WitlessRunner()
_git_runner = GitWitlessRunner()


def _get_annex_version():
    """Return version of available git-annex"""
    try:
        return _runner.run(
            'git annex version --raw'.split(),
            protocol=StdOutErrCapture)['stdout']
    except CommandError:
        # fall back on method that could work with older installations
        out = _runner.run(
            ['git', 'annex', 'version'],
            protocol=StdOutErrCapture)
        return out['stdout'].splitlines()[0].split(':')[1].strip()


def _get_git_version():
    """Return version of git we use (might be bundled)"""
    return __get_git_version()


def _get_system_git_version():
    """Return version of git available system-wide

    Might be different from the one we are using, which might be
    bundled with git-annex
    """
    return __get_git_version(_runner)


def _get_bundled_git_version():
    """Return version of git bundled with git-annex.
    """
    path = _git_runner._get_bundled_path()
    if path:
        out = _runner.run(
            [op.join(path, "git"), "version"],
            protocol=StdOutErrCapture)['stdout']
        # format: git version 2.22.0
        return out.split()[2]


def _get_ssh_version(exe=None):
    """Return version of ssh

    Annex prior 20170302 was using bundled version, then across all systems
    we used system one if installed, and then switched to the one defined in
    configuration, with system-wide (not default in PATH e.g. from conda)
    "forced" on Windows.  If no specific executable provided in `exe`, we will
    use the one in configuration
    """
    if exe is None:
        from datalad import cfg
        exe = cfg.obtain("datalad.ssh.executable")
    out = _runner.run(
        [exe, '-V'],
        protocol=StdOutErrCapture)
    # apparently spits out to err but I wouldn't trust it blindly
    stdout = out['stdout']
    if out['stderr'].startswith('OpenSSH'):
        stdout = out['stderr']
    match = re.match(
        "OpenSSH.*_([0-9][0-9]*)\\.([0-9][0-9]*)(p([0-9][0-9]*))?",
        stdout)
    if match:
        return "{}.{}p{}".format(
            match.groups()[0],
            match.groups()[1],
            match.groups()[3])
    raise AssertionError(f"no OpenSSH client found: {stdout}")


def _get_system_ssh_version():
    """Return version of the default on the system (in the PATH) ssh
    """
    return _get_ssh_version("ssh")


def _get_system_7z_version():
    """Return version of 7-Zip"""
    out = _runner.run(
        ['7z'],
        protocol=StdOutErrCapture)
    # reporting in variable order across platforms
    # Linux: 7-Zip [64] 16.02
    # Windows: 7-Zip 19.00 (x86)
    pieces = out['stdout'].strip().split(':', maxsplit=1)[0].strip().split()
    for p in pieces:
        # the one with the dot is the version
        if '.' in p:
            return p
    lgr.debug("Could not determine version of 7z from stdout. %s", out)


class ExternalVersions(object):
    """Helper to figure out/use versions of the externals (modules, cmdline tools, etc).

    To avoid collision between names of python modules and command line tools,
    prepend names for command line tools with `cmd:`.

    It maintains a dictionary of `distuil.version.LooseVersion`s to make
    comparisons easy. Note that even if version string conform the StrictVersion
    "standard", LooseVersion will be used.  If version can't be deduced for the
    external, `UnknownVersion()` is assigned.  If external is not present (can't
    be imported, or custom check throws exception), None is returned without
    storing it, so later call will re-evaluate fully.
    """

    UNKNOWN = UnknownVersion()

    _CUSTOM = {
        'cmd:annex': _get_annex_version,
        'cmd:git': _get_git_version,
        'cmd:bundled-git': _get_bundled_git_version,
        'cmd:system-git': _get_system_git_version,
        'cmd:ssh': _get_ssh_version,
        'cmd:system-ssh': _get_system_ssh_version,
        'cmd:7z': _get_system_7z_version,
    }
    # ad-hoc hardcoded map for relevant Python packages which do not provide
    # __version__ and are shipped by a differently named pypi package
    _PYTHON_PACKAGES = {  # Python package -> distribution package
        'github': 'pygithub',
    }
    _INTERESTING = (
        'annexremote',
        'platformdirs',
        'boto',
        'exifread',
        'git',
        'gitdb',
        'humanize',
        'iso8601',
        'keyring',
        'keyrings.alt',
        'msgpack',
        'mutagen',
        'patool',
        'cmd:7z',
        'requests',
        'scrapy',
    )

    def __init__(self):
        self._versions = {}
        self.CUSTOM = self._CUSTOM.copy()
        self.INTERESTING = list(self._INTERESTING)  # make mutable for `add`

    @classmethod
    def _deduce_version(klass, value):
        version = None

        # see if it is something containing a version
        for attr in ('__version__', 'version'):
            if hasattr(value, attr):
                version = getattr(value, attr)
                break

        # try pkg_resources
        if version is None and hasattr(value, '__name__'):
            pkg_name = klass._PYTHON_PACKAGES.get(value.__name__, value.__name__)
            try:
                import pkg_resources
                version = pkg_resources.get_distribution(pkg_name).version
            except Exception:
                pass

        # assume that value is the version
        if version is None:
            version = value

        # do type analysis
        if isinstance(version, (tuple, list)):
            #  Generate string representation
            version = ".".join(str(x) for x in version)
        elif isinstance(version, bytes):
            version = version.decode()
        elif isinstance(version, str):
            pass
        else:
            version = None

        if version:
            return LooseVersion(version)
        else:
            return klass.UNKNOWN

    def __getitem__(self, module):
        # when ran straight in its source code -- fails to discover nipy's version.. TODO
        #if module == 'nipy':
        #    import pdb; pdb.set_trace()
        if not isinstance(module, str):
            modname = module.__name__
        else:
            modname = module
            module = None

        lgr.log(5, "Requested to provide version for %s", modname)
        # Early returns None so we do not store prev result for  them
        # and allow users to install things at run time, so later check
        # doesn't pick it up from the _versions
        if modname not in self._versions:
            version = None   # by default -- not present
            if modname in self.CUSTOM:
                try:
                    version = self.CUSTOM[modname]()
                    version = self._deduce_version(version)
                except Exception as exc:
                    lgr.debug("Failed to deduce version of %s due to %s"
                              % (modname, CapturedException(exc)))
                    return None
            else:
                if module is None:
                    if modname not in sys.modules:
                        try:
                            module = __import__(modname)
                        except ImportError:
                            lgr.debug("Module %s seems to be not present", modname)
                            return None
                        except Exception as exc:
                            lgr.warning("Failed to import module %s due to %s",
                                        modname, CapturedException(exc))
                            return None
                    else:
                        module = sys.modules[modname]
                if module:
                    version = self._deduce_version(module)
            self._versions[modname] = version

        return self._versions.get(modname, self.UNKNOWN)

    def keys(self, query=False):
        """Return names of the known modules

        Parameters
        ----------
        query: bool, optional
          If True, we will first query all CUSTOM and INTERESTING entries
          to make sure we have them known.
        """
        if query:
            [self[k] for k in chain(self.CUSTOM, self.INTERESTING)]
        return self._versions.keys()

    def __contains__(self, item):
        return bool(self[item])

    def add(self, name, func=None):
        """Add a version checker

        This method allows third-party libraries to define additional checks.
        It will not add `name` if already exists.  If `name` exists and `func`
        is different - it will override with a new `func`.  Added entries will
        be included in the output of `dumps(query=True)`.

        Parameters
        ----------
        name: str
          Name of the check (usually a name of the Python module, or an
          external command prefixed with "cmd:")
        func: callable, optional
          Function to be called to obtain version information. This should be
          defined when checking the version of something that is not a Python
          module or when this class's method for determining the version of a
          Python module isn't sufficient.
        """
        if func:
            func_existing = self.CUSTOM.get(name, None)
            was_known = False
            if func_existing and func_existing is not func:
                lgr.debug(
                    "Adding a new custom version checker %s for %s, "
                    "old one: %s", func, name, func_existing)
                was_known = name in self._versions
            self.CUSTOM[name] = func
            if was_known:
                # pop and query it again right away to possibly replace with a new value
                self._versions.pop(name)
                _ = self[name]
        elif name not in self.INTERESTING:
            self.INTERESTING.append(name)

    @property
    def versions(self):
        """Return dictionary (copy) of versions"""
        return self._versions.copy()

    def dumps(self, indent=None, preamble="Versions:", query=False):
        """Return listing of versions as a string

        Parameters
        ----------
        indent: bool or str, optional
          If set would instruct on how to indent entries (if just True, ' '
          is used). Otherwise returned in a single line
        preamble: str, optional
          What preamble to the listing to use
        query : bool, optional
          To query for versions of all "registered" custom externals, so to
          get those which weren't queried for yet
        """
        if indent and (indent is True):
            indent = ' '
        items = ["%s=%s" % (k, self._versions[k]) for k in sorted(self.keys(query=query))]
        out = "%s" % preamble if preamble else ''
        if indent is not None:
            if preamble:
                preamble += linesep
            indent = ' ' if indent is True else str(indent)
            out += (linesep + indent).join(items) + linesep
        else:
            out += " " + ' '.join(items)
        return out

    def check(self, name, min_version=None, msg=""):
        """Check if an external (optionally of specified min version) present

        Parameters
        ----------
        name: str
          Name of the external (typically a Python module)
        min_version: str or version, optional
          Minimal version to satisfy
        msg: str, optional
          An additional message to include into the exception message

        Raises
        ------
        MissingExternalDependency
          if the external is completely missing
        OutdatedExternalDependency
          if the external is present but does not satisfy the min_version
        """
        ver_present = self[name]
        if ver_present is None:
            raise MissingExternalDependency(
                name, ver=min_version, msg=msg)
        elif min_version and ver_present < min_version:
            raise OutdatedExternalDependency(
                name, ver=min_version, ver_present=ver_present, msg=msg)


external_versions = ExternalVersions()
