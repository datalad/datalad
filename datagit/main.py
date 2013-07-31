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
from .network import collect_urls, filter_urls, \
      urljoin, download_url
from .utils import pprint_indent

class DoubleAnnexRepo(object):

    def __init__(self):
        pass

#
# Main loop
#
# TODO: formalize existing argument into option (+cmdline option?)
def page2annex(cfg, existing='check',
               dry_run=False, cache=False, db_name = '.page2annex'):
    """Given a configuration fetch/update git-annex "clone"
    """

    # Let's output summary stats at the end
    stats = dict([(k, 0) for k in
                  ['sections', 'urls', 'allurls',
                   'downloads', 'downloaded',
                   'incoming_annex_updates', 'public_annex_updates',
                  ]])
    hot_cache = {}

    runner = Runner(dry=dry_run)
    # convenience shortcuts
    _call = runner.drycall

    dry_str = "DRY: " if dry_run else ""

    dcfg = cfg.get_section('DEFAULT')
    incoming_path = dcfg.get('incoming')
    public_path = dcfg.get('public')

    #
    # Initializing file structure
    #
    if not (os.path.exists(incoming_path) and os.path.exists(public_path)):
        lgr.debug("Creating directories for incoming (%s) and public (%s) annexes"
                  % (incoming_path, public_path))

        if not os.path.exists(incoming_path):
            _call(os.makedirs, incoming_path)
        if not os.path.exists(public_path):
            _call(os.makedirs, public_path)

    # TODO: description might need to be evaluated provided with some
    #       page content
    description = dcfg.get('description')
    public_annex = AnnexRepo(public_path, runner=runner, description=description)

    if public_path != incoming_path:
        incoming_annex = AnnexRepo(incoming_path, runner=runner,
                                   description=description + ' (incoming)')
        # TODO: git remote add public to incoming, so we could
        # copy/get some objects between the two
    else:
        incoming_annex = public_annex

    # TODO: provide AnnexRepo's with the "runner"

    # TODO: load previous status info
    """We need

    incoming -- to track their mtime/size and urls.
      URLs might or might not provide Last-Modified,
      so if not provided, would correspond to None and only look by url change pretty much
      keeping urls would allow for a 'quick' check mode where we would only check
      if file is known

    public_incoming -- to have clear correspondence between public_filename and incoming (which in turn with url).
                   public_filename might correspond to a directory where we would
                   extract things, so we can't just geturl on it
    """

    db_path = os.path.join(incoming_path, db_name)
    if os.path.exists(db_path):
        db = load_db(db_path)
    else:
        # create fresh
        db = dict(incoming={},   # incoming_filename -> (url, mtime, size (AKA Content-Length, os.stat().st_size ))
                  public_incoming={}) # public_filename -> incoming_filename

    db_incoming = db['incoming']
    # reverse map: url -> incoming
    db_incoming_urls = dict([(v['url'], i) for i,v in db_incoming.iteritems()])
    db_public_incoming = db['public_incoming']

    # TODO: look what is in incoming for this "repository", so if
    # some urls are gone or changed so previous file is not there
    # we would clean-up upon exit

    # each section defines a separate download setup
    for section in cfg.sections():
        if section in ('DEFAULT', 'INCLUDES'):
            lgr.debug("Skipping 'housekeeping' section %r" % section)
            continue
        lgr.info("Section: %s" % section)
        stats['sections'] += 1

        # some checks
        scfg = cfg.get_section(section)

        add_mode = scfg.get('mode')
        assert(add_mode in ['download', 'fast', 'relaxed'])
        fast_mode = add_mode in ['fast', 'relaxed']

        repo_sectiondir = scfg.get('directory')

        full_incoming_sectiondir = os.path.join(incoming_annex.path, repo_sectiondir)
        full_public_sectiondir = os.path.join(public_annex.path, repo_sectiondir)

        if not (os.path.exists(incoming_annex.path) and os.path.exists(public_annex.path)):
            lgr.debug("Creating directories for section's incoming (%s) and public (%s) annexes"
                      % (full_incoming_sectiondir, full_public_sectiondir))
            _call(os.makedirs, full_incoming_sectiondir)
            _call(os.makedirs, full_public_sectiondir)           #TODO might be the same

        incoming_destiny = scfg.get('incoming_destiny')
        # Fetching the page (possibly again! thus a dummy hot_cache)
        top_url = scfg['url'].replace('/./', '/')
        if '..' in top_url:
            raise ValueError("Some logic would fail with relative paths in urls, "
                             "please adjust %s" % scfg['url'])
        urls_all = collect_urls(top_url, recurse=scfg['recurse'], hot_cache=hot_cache, cache=cache)


        #lgr.debug("%d urls:\n%s" % (len(urls_all), pprint_indent(urls_all, "    ", "[%s](%s)")))

        # Filter them out
        urls = filter_urls(urls_all, **dict(
            [(k,scfg[k]) for k in
             ('include_href', 'exclude_href',
              'include_href_a', 'exclude_href_a')]))
        lgr.debug("%d out of %d urls survived filtering"
                 % (len(urls), len(urls_all)))
        if len(set(urls)) < len(urls):
            urls = sorted(set(urls))
            lgr.info("%d unique urls" % (len(urls),))
        lgr.debug("%d urls:\n%s"
                  % (len(urls), pprint_indent(urls, "    ", "[%s](%s): %s")))
        if scfg.get('check_url_limit', None):
            limit = int(scfg['check_url_limit'])
            if limit and len(urls) > limit:
                raise RuntimeError(
                    "Cannot process section since we expected only %d urls"
                    % limit)

        #
        # Process urls
        stats['allurls'] += len(urls)
        for href, href_a, link in urls:
            evars = dict(href=href, link=link)

            # bring them into the full urls, href might have been a full url on its own
            href_full = urljoin(top_url, href)
            lgr.debug("Working on [%s](%s)" % (href_full, href_a))

            incoming_updated = False
            incoming_downloaded = False

            # We need to decide either some portion of href path
            # should be "maintained", e.g. in cases where we recurse
            # TODO: make stripping/directories optional/configurable
            # so we are simply deeper on the same site
            href_dir = os.path.dirname(href_full[len(top_url):].lstrip(os.path.sep)) \
                if href_full.startswith(top_url) else ''

            # Download incoming and possibly get alternative filename from Deposit
            # It will adjust db_incoming in-place
            if (href_full in db_incoming_urls
                and (existing and existing == 'skip')):
                lgr.debug("Skipping attempt to download since %s known to db "
                          "already and existing='skip'" % href_full)
                incoming_filename = db_incoming_urls[href_full]
            else:
                incoming_filename, incoming_downloaded, incoming_updated, downloaded_size = \
                  download_url(href_full, incoming_annex.path,
                               os.path.join(repo_sectiondir, href_dir),
                               db_incoming=db_incoming, dry_run=runner.dry, # TODO -- use runner?
                               add_mode=add_mode)
                stats['downloaded'] += downloaded_size

            full_incoming_filename = os.path.join(incoming_annex.path, incoming_filename)

            evars['filename'] = incoming_filename
            public_filename = scfg.get('filename', vars=evars)
            evars['public_filename'] = public_filename

            # Incoming might be an archive -- check and adjust public filename accordingly
            is_archive, public_filename = pretreat_archive(
                public_filename, archives_re=scfg.get('archives_re', vars=evars))

            if incoming_updated and is_archive and fast_mode :
                # there is no sense unless we download the beast
                # thus redo now forcing the download
                lgr.info("(Re)downloading %(href_full)s since points to an archive, thus "
                         "pure fast mode doesn't make sense" % locals())
                incoming_filename_, incoming_downloaded, incoming_updated_, downloaded_size = \
                  download_url(href_full, incoming_annex.path,
                               os.path.join(repo_sectiondir, href_dir),
                               db_incoming=db_incoming, dry_run=runner.dry,
                               add_mode='download',
                               force_download=True)
                assert(incoming_filename == incoming_filename_)
                stats['downloaded'] += downloaded_size
                incoming_updated = incoming_updated_ or incoming_updated

            stats['downloads'] += int(incoming_downloaded)
            if incoming_updated:
                if not dry_run:
                    _call(save_db, db, db_path)   # must go to 'finally'

            annex_updated = False
            # TODO: may be these checks are not needed and we should follow the logic all the time?
            if incoming_updated \
              or (not public_filename in db_public_incoming) \
              or (not lexists(join(public_annex.path, public_filename))):
                # Place the files under git-annex, if they do not exist already
                #if href.endswith('gz'):
                #    import pydb; pydb.debugger()

                # TODO: we might want to get matching to db_incoming stamping into db_public,
                #       so we could avoid relying on incoming_updated but rather comparison of the records
                #  argument #2 -- now if incoming_updated, but upon initial run annex_file fails
                #  for some reason -- we might be left in a state where "public_annex" is broken
                #  upon subsequent run where incoming_updated would be False.  So we really should keep
                #  stamps for both incoming and public to robustify tracking/updates
                incoming_annex_updated, public_annex_updated = \
                  annex_file(
                    href_full,
                    incoming_filename=incoming_filename,
                    incoming_annex=incoming_annex,
                    incoming_updated=incoming_updated,
                    is_archive=is_archive,
                    public_filename=public_filename,
                    public_annex=public_annex,
                    incoming_destiny=incoming_destiny,
                    add_mode=add_mode,
                    addurl_opts=scfg.get('addurl_opts', None, vars=evars),
                    runner=runner,
                    )

                db_public_incoming[public_filename] = incoming_filename
                annex_updated = incoming_annex_updated or public_annex_updated
                stats['incoming_annex_updates'] += int(incoming_annex_updated)
                stats['public_annex_updates'] += int(public_annex_updated)
            else:
                # TODO: shouldn't we actually check???
                lgr.debug("Skipping annexing %s since it must be there already and "
                          "incoming was not updated" % public_filename)

            # TODO: make save_db a handler upon exit of the loop one way or another
            if not dry_run and (annex_updated or incoming_updated):
                _call(save_db, db, db_path)

            stats['urls'] += 1

    stats_str = "Processed %(sections)d sections, %(urls)d (out of %(allurls)d) urls, " \
                "%(downloads)d downloads with %(downloaded)d bytes. " \
                "Made %(incoming_annex_updates)s incoming and %(public_annex_updates)s " \
                "public git/annex additions/updates" % stats

    _call(git_commit,
          incoming_annex.path,
          files=[db_name] if os.path.exists(db_path) else [],
          msg="page2annex(incoming): " + stats_str)
    if incoming_annex is not public_annex:
        _call(git_commit, public_annex.path,
              msg="page2annex(public): " + stats_str)

    lgr.info(stats_str)

    if dry_run:
        # print all accumulated commands
        ## for cmd in runner.commands:
        ##     lgr.info("DRY: %s" % cmd)
        pass
    else:
        # Once again save the DB -- db might have been changed anyways
        save_db(db, db_path)

    return stats
