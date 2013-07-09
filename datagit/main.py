#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""Interfaces to git and git-annex

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

from .repos import *
from .db import load_db, save_db
from .network import fetch_page, parse_urls, filter_urls, \
      urljoin, download_url


def pprint_indent(l, indent="", fmt='%s'):
    return indent + ('\n%s' % indent).join([fmt % x for x in l])

#
# Main loop
#
def rock_and_roll(cfg, dry_run=False, db_name = '.page2annex'):
    """Given a configuration fetch/update git-annex "clone"
    """

    # Let's output summary stats at the end
    stats = dict([(k, 0) for k in
                  ['sections', 'urls', 'downloads', 'annex_updates', 'size']])
    pages_cache = {}

    dry_str = "DRY: " if dry_run else ""

    incoming = cfg.get('DEFAULT', 'incoming')
    public = cfg.get('DEFAULT', 'public')

    #
    # Initializing file structure
    #
    if not (os.path.exists(incoming) and os.path.exists(public)):
        lgr.debug("%sCreating directories for incoming (%s) and public (%s) annexes"
                  % (dry_str, incoming, public))

        if not dry_run:
            if not os.path.exists(incoming):
                os.makedirs(incoming)
            if not os.path.exists(public):
                os.makedirs(public)           #TODO might be the same

    if not os.path.exists(os.path.join(public, '.git', 'annex')):
        public_annex = AnnexRepo(public, dry_run=dry_run)
        description = cfg.get('DEFAULT', 'description')
        public_annex.init(description)
        if public != incoming:
            incoming_annex = AnnexRepo(incoming, dry_run=dry_run)
            incoming_annex.init(description + ' (incoming)')
        else:
            incoming_annex = public_annex

    # TODO: load previous status info
    """We need

    url_stamps -- to track their time.  URLs might or might not provide Last-Modified,
      so if not provided, would correspond to None and only look by url change pretty much

    annex_pairs -- to have clear correspondence between annex_filename and url.
                   annex_filename might correspond to a directory where we would
                   extract things, so we can't just geturl on it
    """

    db_path = os.path.join(incoming, db_name)
    if os.path.exists(db_path):
        status_info = load_db(db_path)
    else:
        # create fresh
        status_info = dict(url_stamps={},   # url -> (mtime, size (AKA Content-Length, os.stat().st_size ))
                           annex_pairs={})      # annex_filename -> url

    url_stamps = status_info['url_stamps']
    annex_pairs = status_info['annex_pairs']

    # TODO: look what is in incoming for this "repository", so if
    # some urls are gone or changed so previous file is not there
    # we would clean-up upon exit

    # each section defines a separate download setup
    for section in cfg.sections():
        lgr.info("Section: %s" % section)
        stats['sections'] += 1

        # some checks
        add_mode = cfg.get(section, 'mode')
        assert(add_mode in ['download', 'fast'])

        section_dir = cfg.get(section, 'directory')

        incoming_section = os.path.join(incoming, section_dir)
        public_section = os.path.join(public, section_dir)

        if not (os.path.exists(incoming) and os.path.exists(public)):
            lgr.debug("%sCreating directories for section's incoming (%s) and public (%s) annexes"
                      % (dry_str, incoming_section, public_section))
            if not dry_run:
                os.makedirs(incoming_section)
                os.makedirs(public_section)           #TODO might be the same

        scfg = dict(cfg.items(section))

        archives_destiny = scfg.get('archives_destiny')
        if archives_destiny == 'auto':
            archives_destiny = 'rm' if incoming == public else 'annex'

        # Fetching the page (possibly again! TODO: cache)
        url = scfg['url']
        page = pages_cache.get(url, None) or fetch_page(url)
        pages_cache[url] = page

        #
        # Parse out all URLs, as a tuple (url, a(text))
        urls_all = parse_urls(page)
        lgr.info("Got total %d urls" % len(urls_all))
        #lgr.debug("%d urls:\n%s" % (len(urls_all), pprint_indent(urls_all, "    ", "[%s](%s)")))

        # Filter them out
        urls = filter_urls(urls_all, **dict(
            [(k,scfg[k]) for k in
             ('include_href', 'exclude_href', 'include_href_a', 'exclude_href_a')]))
        lgr.info("%d out of %d urls survived filtering" % (len(urls), len(urls_all)))
        if len(set(urls)) < len(urls):
            urls = sorted(set(urls))
            lgr.info("%d unique urls" % (len(urls),))
        lgr.debug("%d urls:\n%s" % (len(urls), pprint_indent(urls, "    ", "[%s](%s)"))) 
        if scfg.get('check_url_limit', None):
            limit = int(scfg['check_url_limit'])
            if limit:
                if len(urls) > limit:
                    raise RuntimeError("Cannot process section since we expected only %d urls"
                                       % limit)

        #
        # Process urls
        for href, href_a in urls:
            # bring them into the full urls
            href = urljoin(scfg['url'], href)
            lgr.debug("Working on [%s](%s)" % (href, href_a))

            # Will adjust url_stamps in-place
            filename, full_filename, href_updated = \
              download_url(href, incoming_section, url_stamps=url_stamps, dry_run=dry_run,
                           fast_mode=add_mode=='fast')

            if href_updated:
                stats['downloads'] += 1
                stats['size'] += os.stat(full_filename).st_size
                if not dry_run:
                    save_db(status_info, db_path)
                pass

            # figure out what should it be -- interpolate
            annex_filename = scfg['filename'].replace('&', '%') % locals()
            annex_full_filename = os.path.join(public_section, annex_filename)

            annex_updated = False
            if href_updated or (not annex_filename in annex_pairs):

                # TODO: here figure it out either it will be a
                # directory or not and either it needs to be extracted,
                # and what will be the extracted directory name

                # Place them under git-annex, if they do not exist already
                annex_file(
                    href,
                    incoming_filename=full_filename,
                    annex_filename=annex_full_filename,
                    incoming_annex=incoming_annex,
                    public_annex=public_annex,
                    archives_destiny=archives_destiny,
                    archives_re=scfg.get('archives_re'),
                    add_mode=add_mode,
                    addurl_opts=scfg.get('addurl_opts', None),
                    dry_run=dry_run,
                    )

                annex_pairs[annex_filename] = href
                annex_updated = True
                stats['annex_updates'] += 1
            else:
                # TODO: shouldn't we actually check???
                lgr.debug("Skipping annexing %s since it must be there already"
                          % annex_filename)

            if not dry_run and (annex_updated or href_updated):
                save_db(status_info, db_path)

            stats['urls'] += 1

    git_commit(incoming, files=[db_name])
    if incoming != public:
        git_commit(public)

    lgr.info("Processed %(sections)d sections, %(urls)d urls, "
             "%(downloads)d downloads with %(size)d bytes. Made %(annex_updates)s git/annex additions/updates" % stats)
    return stats
