#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

from os.path import join

from .utils import *

from ..api import *

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

[section1]
# mixing both string interpolations and evaluation
v5_e = "%%.2f(%(v1)s)" %% (var+1)
var_e = "%%.2f" %% (var+2)
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

    #eq_(scfg.get('v3'), '3.bak')
