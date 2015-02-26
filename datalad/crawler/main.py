# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interfaces to git and git-annex

"""


from os.path import dirname, exists, join, sep as pathsep

from ..db import load_db, save_db
from ..support.repos import *
from ..support.network import collect_urls, filter_urls, \
      urljoin, download_url_to_incoming
from ..support.pprint import pprint_indent


class DoubleAnnexRepo(object):
    """TODO: proper docs/motivation for this beast
    """

    def __init__(self, cfg, db_name='.page2annex'):
        self.cfg = cfg
        self.db_name = db_name

        #self.incoming = None
        #self.public = None
        self.runner = None

        self.__init()

    def __init(self):
        pass

    #
    # Main loop
    #
    # TODO: formalize existing argument into option (+cmdline option?)
    def page2annex(self, existing='check', dry_run=False, cache=False):
        """Fetch/update git-annex "clone"
        """

        # Let's output summary stats at the end
        stats = dict([(k, 0) for k in
                      ['sections', 'urls', 'allurls',
                       'downloads', 'downloaded',
                       'incoming_annex_updates', 'public_annex_updates',
                      ]])
        hot_cache = {}
        urls_errored = []

        if self.runner is None:
            self.runner = Runner()

        # TODO: should it be a local 'runner' so we do not augment
        # bound runner humidity permanently
        self.runner.dry = dry_run

        # convenience shortcuts
        _call = self.runner.drycall

        dcfg = self.cfg.get_section('DEFAULT')
        incoming_path = dcfg.get('incoming')
        public_path = dcfg.get('public')

        #
        # Initializing file structure
        #
        if not (exists(incoming_path) and exists(public_path)):
            lgr.debug("Creating directories for incoming (%s) and public (%s) annexes"
                      % (incoming_path, public_path))

            if not exists(incoming_path):
                _call(os.makedirs, incoming_path)
            if not exists(public_path):
                _call(os.makedirs, public_path)

        # TODO: description might need to be evaluated provided with some
        #       page content
        description = dcfg.get('description')
        public_annex = AnnexRepo(public_path, runner=self.runner, description=description)

        if public_path != incoming_path:
            incoming_annex = AnnexRepo(incoming_path, runner=self.runner,
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

        db_path = join(incoming_annex.path, self.db_name)
        if exists(db_path):
            db = load_db(db_path)
        else:
            # create fresh
            db = dict(incoming={},   # incoming_filename -> (url, mtime, size (AKA Content-Length, os.stat().st_size ))
                      public_incoming={}) # public_filename -> incoming_filename

        db_incoming = db['incoming']
        # reverse map: url -> incoming
        db_public_incoming = db['public_incoming']

        # TODO: look what is in incoming for this "repository", so if
        # some urls are gone or changed so previous file is not there
        # we would clean-up upon exit
        db_incoming_urls = dict([(v['url'], i) for i,v in db_incoming.iteritems()])

        # each section defines a separate download setup
        for section in self.cfg.sections():
            if section in ('DEFAULT', 'INCLUDES'):
                lgr.debug("Skipping 'housekeeping' section %r" % section)
                continue
            lgr.info("Section: %s" % section)
            stats['sections'] += 1

            # some checks
            scfg = self.cfg.get_section(section)

            git_add_re = re.compile(scfg.get('git_add')) if scfg.get('git_add') else None
            repo_sectiondir = scfg.get('directory')

            full_incoming_sectiondir = join(incoming_annex.path, repo_sectiondir)
            full_public_sectiondir = join(public_annex.path, repo_sectiondir)

            if not (exists(incoming_annex.path) and exists(public_annex.path)):
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
            #import pdb; pdb.set_trace()

            #lgr.debug("%d urls:\n%s" % (len(urls_all), pprint_indent(urls_all, "    ", "[%s](%s)")))

            # Filter them out; TODO: might better be done within collect_urls?
            urls = filter_urls(urls_all, **dict(
                [(k, scfg[k]) for k in
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
                # Get a dict with all the options
                # yoh: got disracted and lost a thought why this
                #      wasn't finished and either it is needed at all
                # evars = scfg.get_raw_options()
                # evars.update(
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
                href_dir = dirname(href_full[len(top_url):].lstrip(pathsep)) \
                    if href_full.startswith(top_url) else ''

                add_mode = scfg.get('mode')
                assert(add_mode in ['download', 'fast', 'relaxed'])

                # If file name matches git_add, then mode needs to be forced to 'download'
                # TODO: Unfortunately ATM (at least) incoming_filename is deduced later
                # since might be different when fetched.  So for now
                # use URL to judge either the file needs to be added to GIT.
                # I will add below a check that if git_add_re and filename matches
                # but wasn't git_add -- ERROR
                git_add = git_add_re and git_add_re.search(href_full)
                if git_add:
                    add_mode = 'download'
                fast_mode = add_mode in ['fast', 'relaxed']

                # Download incoming and possibly get alternative
                # filename from Deposit It will adjust db_incoming in-place
                if (href_full in db_incoming_urls
                    and (existing and existing == 'skip')):
                    lgr.debug("Skipping attempt to download since %s known to "
                              "db already and existing='skip'" % href_full)
                    incoming_filename = db_incoming_urls[href_full]
                else:
                    try:
                        incoming_filename, incoming_downloaded, incoming_updated, downloaded_size = \
                          download_url_to_incoming(href_full, incoming_annex.path,
                                       join(repo_sectiondir, href_dir),
                                       db_incoming=db_incoming, dry_run=self.runner.dry, # TODO -- use runner?
                                       add_mode=add_mode)
                    except Exception, e:
                        lgr.warning("Skipping %(href_full)s due to error: %(e)s" % locals())
                        urls_errored.append(((href, href_a), e))
                        continue
                    stats['downloaded'] += downloaded_size

                if not git_add and git_add_re and git_add_re.search(incoming_filename):
                    raise RuntimeError("For now git_add pretty much operates on URLs, not files."
                        " But here we got a filename (%s) which matches git_add regexp while original"
                        " url (%s) didn't. TODO" % (incoming_filename, href_full))
                full_incoming_filename = join(incoming_annex.path, incoming_filename)

                evars['filename'] = incoming_filename
                public_filename = scfg.get('filename', vars=evars)
                evars['public_filename'] = public_filename
                # TODO: seems if public == incoming, and would like custom filename_e then there is a problem
                #       and file doesn't get a new name
                # Incoming might be an archive -- check and adjust public filename accordingly
                is_archive, public_filename = pretreat_archive(
                    public_filename, archives_re=scfg.get('archives_re', vars=evars))

                if incoming_updated and is_archive and fast_mode :
                    # there is no sense unless we download the beast
                    # thus redo now forcing the download
                    lgr.info("(Re)downloading %(href_full)s since points to an archive, thus "
                             "pure fast mode doesn't make sense" % locals())
                    incoming_filename_, incoming_downloaded, incoming_updated_, downloaded_size = \
                      download_url_to_incoming(href_full, incoming_annex.path,
                                   join(repo_sectiondir, href_dir),
                                   db_incoming=db_incoming, dry_run=self.runner.dry,
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
                        runner=self.runner,
                        git_add=git_add,
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

#                # TODO: for now we will just post-hoc treat git-annex
#                # downloaded files which needed to be added directly
#                # to git.  Ideally they should not even be added to
#                # git-annex at any point, but code is a mess ATM.
#                if git_add:
#                    for filename in (incoming_filename, public_filename):
#                        assert(os.path.exists(filename))
#                        assert
                stats['urls'] += 1

        stats_str = "Processed %(sections)d sections, %(urls)d (out of %(allurls)d) urls, " \
                    "%(downloads)d downloads with %(downloaded)d bytes. " \
                    "Made %(incoming_annex_updates)s incoming and %(public_annex_updates)s " \
                    "public git/annex additions/updates" % stats

        _call(git_commit,
              incoming_annex.path,
              files=[self.db_name] if exists(db_path) else [],
              msg="page2annex(incoming): " + stats_str)
        if incoming_annex is not public_annex:
            _call(git_commit, public_annex.path,
                  msg="page2annex(public): " + stats_str)


        if dry_run and lgr.getEffectiveLevel() <= logging.INFO:
            # print all accumulated commands
            for cmd in self.runner.commands:
                 lgr.info("DRY: %s" % cmd)
        else:
            # Once again save the DB -- db might have been changed anyways
            save_db(db, db_path)

        lgr.info(stats_str)
        if len(urls_errored):
            lgr.warning("Following urls failed to download")
            for (href, href_a), error in urls_errored:
                lgr.warning("| %s<%s>: %s" % (href_a, href, error))

        return stats
