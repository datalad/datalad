#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from setuptools import setup

import versioneer
from _datalad_build_support.setup import (
    BuildConfigInfo,
    BuildManPage,
)

cmdclass = {
    "build_manpage": BuildManPage,
    # 'build_examples': BuildRSTExamplesFromScripts,
    "build_cfginfo": BuildConfigInfo,
    # 'build_py': DataladBuild
}
cmdclass = versioneer.get_cmdclass(cmdclass)

setup(cmdclass=cmdclass)
