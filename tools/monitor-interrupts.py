#!/usr/bin/python
#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""

 COPYRIGHT: Yaroslav Halchenko 2015

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
__copyright__ = 'Copyright (c) 2015 Yaroslav Halchenko'
__license__ = 'MIT'

import re, numpy as np, time

reline = re.compile('(?P<int>[^:]*):(?P<counts>[\s0-9]*)(?P<desc>.*$)')
fname = '/proc/interrupts'

counts = None
while True:
    with open(fname) as f:
        old_counts = counts
        lines = f.readlines()
        cpus = lines[0].split()
        names, counts_list, totals = [], [], []
        for l in lines[1:]:
            r = reline.match(l)
            d = r.groupdict()
            c = map(int, d['counts'].split())
            if len(c) != len(cpus):
                totals.append(l)
            else:
                counts_list.append(c)
                names.append((d['int'], d['desc']))
        counts = np.array(counts_list)
        assert(counts.ndim == 2)
        names = np.array(names) # to ease indexing
        if old_counts is not None:
            # do reporting of most active ones
            diff = counts - old_counts
            maxdiff = np.max(diff)
            strformat = "%%%ds" % (max(np.log10(maxdiff)+1, 4))
            diff_total = np.sum(diff, axis=1)
            most_active = np.argsort(diff_total)[::-1]
            print " "*37 + ' '.join([strformat%c for c in ['TOTAL'] + cpus])
            for name, dt, d in zip(names[most_active], diff_total[most_active], diff[most_active])[:5]:
                print "%4s %30s: %s %s" % (name[0], name[1], strformat%dt, ' '.join([strformat % x for x in d]))
            print ''.join(totals)
        time.sleep(1)

