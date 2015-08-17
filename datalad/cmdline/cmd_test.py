# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run internal DataLad (unit)tests to verify correct operation on the system"""


__docformat__ = 'restructuredtext'

# magic line for manpage summary
# man: -*- % run DataLad's unit-tests

def setup_parser(parser):
    # TODO -- pass options such as verbosity etc
    pass
    
def run(args):
    import datalad
    datalad.test()
