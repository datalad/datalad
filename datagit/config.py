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
#-----------------\____________________________________/------------------

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

from ConfigParser import ConfigParser

from .files import DECOMPRESSORS

#
# Configuration
#
def get_default_config(sections={}):
    cfg = ConfigParser(defaults=dict(
        mode='download',                 # TODO -- check, use
        orig='auto',                 # TODO -- now we don't use it
        meta_info='True',                 # TODO -- now we just use it
        directory="%(__name__)s",
        archives_re='(%s)' % ('|'.join(DECOMPRESSORS.keys())),
        # 'keep'  -- just keep original without annexing it etc
        # 'annex' -- git annex addurl ...
        # 'drop'  -- 'annex add(url)' and then 'annex drop' upon extract
        # 'rm'    -- remove upon extraction if archive
        # 'auto':
        # if incoming == public:
        #  'auto' == 'rm' if is_archive and 'annex' if
        # else:
        #  'auto' == 'annex'
        incoming_destiny="auto",
        # TODO:
        # maintain - preserve the ones in the archive and place them
        #            at the same level as the archive file (TODO)
        # strip - would remove leading extracted directory if a single one
        archives_directories="strip",
        incoming="repos/incoming/EXAMPLE",
        public="repos/public/EXAMPLE",
        include_href='',
        include_href_a='',
        exclude_href='',
        exclude_href_a='',
        filename='filename',
        # Checks!
        check_url_limit='0',                     # no limits
        # unused... we might like to enable it indeed and then be
        # smart with our actions in extracting archives into
        # directories which might contain those files, so some might
        # need to be annexed and some directly into .git
        # TODO
        #annex='.*',                    #
        recurse=None,                     # do not recurse by default, otherwise regex on urls to assume being for directories
        ))
    for section, options in sections.iteritems():
        if section != 'DEFAULT':
            cfg.add_section(section)
        for opt, value in options.iteritems():
            cfg.set(section, opt, value)
    return cfg

def load_config(configs):
    # Load configuration
    cfg = get_default_config()
    cfg_read = cfg.read(configs)
    assert cfg_read == configs, \
           "Not all configs were read. Wanted: %s Read: %s" % (configs, cfg_read)
    return cfg
