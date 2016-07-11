# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the duecredit package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to help maintain a registry of versions for external modules etc
"""
import sys
from os import linesep
from six import string_types

from distutils.version import StrictVersion, LooseVersion

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


class ExternalVersions(object):
    """Helper to figure out/use versions of the external modules.

    It maintains a dictionary of `distuil.version.StrictVersion`s to make
    comparisons easy.  If version string doesn't conform the StrictVersion
    LooseVersion will be used.  If version can't be deduced for the module,
    'None' is assigned
    """

    UNKNOWN = UnknownVersion()

    def __init__(self):
        self._versions = {}

    @classmethod
    def _deduce_version(klass, module):
        version = None
        for attr in ('__version__', 'version'):
            if hasattr(module, attr):
                version = getattr(module, attr)
                break

        if isinstance(version, tuple) or isinstance(version, list):
            #  Generate string representation
            version = ".".join(str(x) for x in version)

        if version:
            try:
                return StrictVersion(version)
            except ValueError:
                # let's then go with Loose one
                return LooseVersion(version)
        else:
            return klass.UNKNOWN

    def __getitem__(self, module):
        # when ran straight in its source code -- fails to discover nipy's version.. TODO
        #if module == 'nipy':
        #    import pdb; pdb.set_trace()
        if not isinstance(module, string_types):
            modname = module.__name__
        else:
            modname = module
            module = None

        if modname not in self._versions:
            if module is None:
                if modname not in sys.modules:
                    try:
                        module = __import__(modname)
                    except ImportError:
                        return None
                else:
                    module = sys.modules[modname]

            self._versions[modname] = self._deduce_version(module)

        return self._versions.get(modname, self.UNKNOWN)

    def keys(self):
        """Return names of the known modules"""
        return self._versions.keys()

    def __contains__(self, item):
        return item in self._versions

    @property
    def versions(self):
        """Return dictionary (copy) of versions"""
        return self._versions.copy()

    def dumps(self, indent=False, preamble="Versions:"):
        """Return listing of versions as a string

        Parameters
        ----------
        indent: bool or str, optional
          If set would instruct on how to indent entries (if just True, ' '
          is used). Otherwise returned in a single line
        preamble: str, optional
          What preamble to the listing to use
        """
        if indent and (indent is True):
            indent = ' '
        items = ["%s=%s" % (k, self._versions[k]) for k in sorted(self._versions)]
        out = "%s" % preamble
        if indent:
            out += (linesep + indent).join([''] + items) + linesep
        else:
            out += " " + ' '.join(items)
        return out


external_versions = ExternalVersions()
