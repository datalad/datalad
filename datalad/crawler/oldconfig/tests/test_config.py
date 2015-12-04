# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from datalad.tests.utils import *

from ..base import load_config

@with_tempfile(suffix='.cfg')
def test_eval_value(filename):
    with open(filename, 'w') as f:
        f.write("""
[DEFAULT]
v1 = 1+2
# simple evaluation
v2_e = str(1+2)
# Simple string interpolations
v4 = %(var)s
# mixing both string interpolations and evaluation
exec = from math import e

       func = lambda x: "fun^%%d" %% x
# Function to be evaluated with some local variable substitution
funccall_e = func(%(l)s)


[section1]
v5_e = "%%.2f(%(v1)s)" %% (var+1)
var_e = "%%.2f" %% (var+2)
e_e = e
v1_array_e = [%(v1)s]
l = 3

[section2]
l = 4

[section3]
l = 1
exec = func = lambda x: "NEW"
""")

# this one is a tricky one -- probably could still work via iterative refinement of vars
# while catching InterpolationMissingOptionError
# v3 = %(v2)s.bak

    cfg = load_config([filename])
    dcfg = cfg.get_section('DEFAULT')
    eq_(dcfg.get('v1'), '1+2')
    eq_(dcfg.get('v2_e'), '3')
    eq_(dcfg.get('v2_e', raw=True), 'str(1+2)')
    eq_(dcfg.get('v2'), '3')
    eq_(dcfg.get('v4', vars=dict(var='1.3333')), '1.3333')

    scfg1 = cfg.get_section('section1')
    eq_(scfg1.get('v5', vars=dict(var=1.3333)), '2.33(1+2)')
    eq_(scfg1.get('var', vars=dict(var=1.3333)), '3.33')
    # now check if exec worked correctly and enriched environment
    # for those evaluations
    import math
    eq_(scfg1.get('e'), math.e)
    eq_(scfg1.get('v1_array'), [ 3 ])
    eq_(scfg1.get('funccall'), 'fun^3')

    scfg2 = cfg.get_section('section2')
    eq_(scfg2.get('funccall'), 'fun^4')

    scfg3 = cfg.get_section('section3')
    # exec was redefined
    eq_(scfg3.get('funccall'), 'NEW')
    eq_(scfg3.get('l'), '1')

