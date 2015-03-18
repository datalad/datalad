#emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
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

import re
import os
import bs4
import time

def slugify(value):
    """Normalizes the string: removes non-alpha characters.
    """
    import unicodedata
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s-]', '', value).strip())
    return value

def get_video_filename(link, filename):
    video_entry = list(link.parents)[3] # <div class="article">
    assert(isinstance(video_entry, bs4.element.Tag))
    bold_entries = video_entry.find_all('b')
    assert(len(bold_entries) == 2)      # that is what we know atm
    title = bold_entries[0].text
    date_ = bold_entries[1].text
    # Parse/convert the date
    date = time.strptime(date_, '%A, %B %d, %Y')
    date_str = time.strftime('%Y/%m-%d', date)
    # try to find extension in the filename
    ext = os.path.splitext(filename)[1]
    if not ext or len(ext) > 5:
        # For now just hope that it is a video extension...
        # TODO -- check with mime ... etc?
        ext = '.avi'
    return "%s - %s%s" % (date_str, slugify(title), ext)
