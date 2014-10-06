Thoughts about redesign, well actually "design" since originally there
were none, of datalad crawl.

Global portion of the config
============================

::

  [datasethandle]
  path =
  description = 
  exec = 

Data providers
==============

`crawl` command collects data present possibly across
different remote data providers (regular HTTP websites, AWS S3
buckets, etc) and then consolidates access to them within a single
git-annex'ed repository.  `crawl` should also keep track of
status/versions of the files, so in case of the updates (changes,
removals, etc) on remote sites, git-annex repository could be
correspondingly updated.

Common config specs::

    [provider:XXX]
    type = (web|s3http|merge|git-annex) # default to web
    branch = master              # default to master
    commit_to_git =              # regexps of file names to commit directly to git
    ignore =                     # files to ignore entirely
    drop = False                 # either to drop the load upon 'completion'
    # some sanity checks
    check_entries_limit = -1     # no limit by default


(To be) Supported data providers
--------------------------------

Web
~~~

In many usecases data are hosted on a public portal, lab website,
personal page, etc.  Such data are often provided in tarballs, which
need to be downloaded and extracted later on.  Extraction will not be
a part of this provider -- only download from the web::

    [provider:incoming_http]
    type = web
    mode = (download|fast|relaxed)            # fast/relaxed/download
    filename = (url|request)                  # of cause also could be _e'valuated given the bs4 link get_video_filename(link, filename)
    recurse_(a|href) =                        # regexes to recurse
    # mimicing scrapy
    start_urls = http://...                   #
    certificates =                            # if there are https -- we need to allow specifying those
    allowed_domains = example.com/buga/duga   # to limit recursion
                      sample.com
    excluded_hrefs =                          # do not even search for "download" URLs on given pages.  Should also allow to be a function/callback to decide based on request?
    include_(a|href) =                        # what to download
    exclude_(a|href) =                        # and not (even if matches)
    ???generators = generate_readme              # Define some additional actions to be performed....

We need to separate options for crawling (recursion etc) and deciding
what to download/annex.

Q: should we just specify xpath's for information to get extracted
   from a response corresponding to a matching url?  just any crawled page?

Q: allow to use xpath syntax for better control of what to recurse/include?

Q: authentication -- we should here relate to the Hostings
!: scrapy's Spider provides start_requests() which could be used to
   initiate the connection, e.g. to authenticate and then use that connection.
   Authentication detail must not be a part of the configuration, BUT
   it must know HOW authentication should be achieved.  In many cases could
   be a regular netrc-style support (so username/password).

   Those authenticators should later be reused by "download clients"

Q: we might need to worry/test virtually about every possible associated
   to http downloads scenario, e.g. support proxy (with authentication).
   May be we could just switch to aria2 and allow to specify access options?

Q: may be (a new provider?) allow to use a scrapy spider's output to
   harvest the table of links which need to be fetched



Use cases to keep in mind
+++++++++++++++++++++++++

- versioning present in the file names
  ftp://ftp.ncbi.nlm.nih.gov/1000genomes/ftp/sequence_indices/

  - ha -- idea, all those should be referred in some other branch, like
    with archives, and then 'public' one would just take care about
    pointing to the "correct one" and serve a "compressed" view.
    Hence: monitor original, point "compressed" to a branch giving it
    a set of rules on how to determine version, i.e. on which files
    This way we could have both referenced in the same repository.


Amazon S3
~~~~~~~~~

Initial accent will be made on S3 buckets which have versioning
enabled, and which expose their content via regular http/https.

tricky points:
- versioning (must be enabled. If uploaded before enabled, version is Null)

- etags are md5s BUT only if upload was not multi-chunked, so
  it becomes difficult to identify files by md5sums (must be
  downloaded first then, or some meta-info of file should be modified so
  etag gets regenerated -- should result in file md5sum appearing as etag)

- S3 most probably would be just an additional -- not the primary provider


Generated
~~~~~~~~~

We should allow for files to be generated based on the content of the
repository and/or original information from the data providers,
e.g. content of the webpages containing the files to be
downloaded/referenced.  Originally envisioned as a separate branch,
where only archived content would be downloaded and later extracted
into corresponding locations of the "public" branch (e.g. master).

But may be it should be more similar to the stated above "versioning"
idea where it would simply be an alternative "view" of another branch,
where some content is simply extracted.  I.e. all those modifications
could be assembled as a set of "filters"::

    [generator:generate_readme]
    filename = README.txt
    content_e = generate_readme(link, filename)  # those should be obtained/provided while crawling

or

    [generator:fetch_license]
    filename = LICENSE.txt
    content_e = fetch_license(link, filename)  # those should be obtained/provided while crawling


Merge
~~~~~

Originally fetched Files might reside in e.g. 'incoming' branch while
'master' branch then could be 'assembled' from few other branches with
help of filtering::

    [provider:master]
    type = merge
    branch = master # here matches the name but see below if we need to repeat
    merge = incoming_data_http
            incoming_meta_website
    filters = extract_models
              extract_data
              generate_some_more_files_if_you_like


Q: should we may be 'git merge --no-commit' and then apply the
   filters???

   probably not since there could be conflicts if similarly named file
   is present in target branch (e.g. generated) and was present
   (moved/renamed via filters) in the original branch.

Q: but merging of branches is way too cool and better establishes the
   'timeline' and dependencies...
   So merge should be done "manually" by doing (there must be cleaner way)::

     git merge -s ours --no-commit
     git rm -r *
     # - collect and copy files for all the File's from branches to .
     # - stage all the files
     # - pipe those "File"s from all the branches through the filters
     #   (those should where necessary use git rm, mv, etc)
     # - add those File's to git/git-annex
     git commit

   but what if a filter (e.g. cmd) requires current state of files from
   different branches?...  all possible conflict problems could be
   mitigated by storing content in branches under some directories,
   then manipulating upon "merge" and renaming before actually 'git merging'


Q: what about filters per incoming branch???  we could options for
   filters specification
   (e.g. extract_models[branches=incoming_data_http]) or allow
   only regular 2-edge merge at a time but multiple times...


XNAT, COINS, ...
~~~~~~~~~~~~~~~~

Later ... but the idea should be the same I guess: they should expose
collections of File's with a set of URIs so they could be addurl'ed to
the files.  It is not clear yet either they would need to be crawled
or would provide some API similar to S3 to request all the necessary
information?


git/git-annex
~~~~~~~~~~~~~

If provider is already a Git(-annex) repository.  Usecase:
forrest_gump.  So it is pretty much a regular remote **but** it might
benefit from our filters etc.


torrent
~~~~~~~

I guess similar/identical to archives if torrent points to a single
file -- so just 'addurl'.  If torrent provides multiple files, would
need mapping of UUIDs I guess back to torrents/corresponding files.
So again -- similar to archives...?

aria2 seems to provide a single unified HTTP/HTTPS/FTP/BitTorrent
support, with fancy simultaneous fetching from multiple
remotes/feeding back to the torrent swarm (caution for non-free data).
It also has RPC support, which seems to be quite cool and might come
handy (e.g. to monitor progress etc)


Wild: Git repository for being rewritten
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

theoretically we could collect all the information to rewrite some
other Git repo but now injecting some files into git-annex (while
possibly even pointing for the load to e.g. original SVN repo).

Tricky:
- branches and merges -- would be really tricky and so far not
  envisioned how
- "updates" should correspond to commits in original repository
- all the commit information should be extracted/provided for the
  commit here


Filters
=======

Considering idea that all the modifications (archives extraction,
versioning etc) could be made through monitoring of another branch(es)
and applying a set of filters.

- files which aren't modified, should also propagate into target
  branch, along with all their urls

  file by file wouldn't work since filter might need to analyze the
  entire list of files...::

      def apply_filters(self):
       files_out = files_in
       for filter in self.filters:
        files_out = filter.apply(files_out)
       return files_out

  then each filter would decide on how to treat the list of files.
  May be some filters' subtyping would be desired
  (PerfileFilter/AllfilesFilter)

- filters should provide API to 'rerun' their action to obtain the
  same result.


Cross-branch
------------

Some filters to be applied on files from one branch to have results
placed into another:


Extract
~~~~~~~

Special kind of a beast: while keeping the original archive under
git-annex obtained from any other provider (e.g. 'Web'), we extract
the load (possibly with some filtering/selection):

  Q: how to deal with extract from archives -- extraction should
     better be queued to extract multiple files from the archive at
     once.  But ATM it would not happen since all those URIs will
     simply be requested by simple wget/curl calls by git-annex file
     at a time.
  A: upon such a first call, check if there is .../extracted_key/key/, if
     there is -- use.  If not -- extract and then use. use = hardlink
     into the target file.
     Upon completion of `datalad get` (or some other command) verify
     that all `/extracted/` are removed (and/or provide setting -- may
     be we could/should just keep those around)


Config Examples:
++++++++++++++++

::

    [filter:extract_models]
    filter = extract               # by default would be taken as the element after "filter:"
    input = *(\S+)_models\.tgz$    # and those files are not provided into output
    output_prefix = models/$1/     # somehow we should allow to reuse input regex's groups
    exclude =                      # regex for files to be excluded from extraction or straight for tar?
    strip_path = 1

Probably will just use patoolib (do not remember if has
strip_path... seems not:
https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=757483)

URI:  dl:extract:UID

and we keep information for what 'key' it came into what file (which
might later get renamed, so extraction from the archive shouldn't
later happen in-place, but rather outside and then moved accordingly)

Tricky point(s):

- may be by default should still extract all known archives types and
  just rely on the filename logic?
- the same file might be available from multiple archives.
  So we would need to keep track from previous updates, from which
  archive files could be fetched.
  - how to remove if archive is no longer avail?
    probably some fsck should take care about checking if archives
    are still avail, and if not -- remove the url

- keep track which files came from the archive, so we could later
  remove them happen if archive misses the file now.

Q: allow for 'relaxed' handling?
   If tarballs are not versioned at all, but we would like to create
   overall (? or just per files) 'relaxed' git-annex?

   Probably no complication if URIs will be based (natively) on the
   fast or relaxed keys.  Sure thing things would fail if archive was
   changed and lacks the file.

Q: hm -- what about MD5SUM checking? e.g. if archive was posted with
   the MD5SUMs file

   I guess some kind of additional filter which could be attached
   somehow?


Move/Rename/Delete
~~~~~~~~~~~~~~~~~~

Just move/rename/delete some files around e.g. for a custom view of
the dataset (e.g. to conform openfmri layout). Key would simply be
reused ;)

Q: should it be 'Within-branch' filter?


Command
~~~~~~~

A universal filter which would operate on some files and output
possibly in place or modified ones...

Then it would need to harvest and encode into file's URI the
provenance -- i.e. so it could later be recreated automagically.

For simple usecases (e.g. creation of lateralized atlas in HOX, some
data curation, etc)

URI:  dl:cmd:UID

while we keep a file providing the corresponding command for each UID,
where ARGUMENTS will would point to the original files keys in the git
annex.   Should it be kept in PROV format may be???

Config Examples::

    [filter:command_gunzip]
    in1 = *\.gz
    in2_e = in1.replace('.gz', '')
    #eval_order=in1 in2
    command = zcat {in1} > {in2}
    output_files = {in2}

Problems:

- might be tricky to provide generic enough interface?
- we need plentiful of use-cases to get it right, so this one is just
  to keep in mind for future -- might be quite cool after all.


Within-branch
-------------

Other "Filters" should operate within the branch, primarily simply for
checking the content


Checksum
~~~~~~~~

e.g. point to MD5SUMS file stored in the branch, provide how file
names must be augmented, run verification -- no files output, just the
status

Addurl
~~~~~~

If the repository is going/was published also online under some URL.
We might like to populate files with corresponding urls.

    [filter:addurl]
    prefix = http://psydata.ovgu.de/forrest_gump/.git/annex/
    check = (False|True)  # to verify presence or not ???

Usecase -- Michael's forrest_gump repository.  Now files are not
associated explicitly with that URL -- only via a regular git remote.
This cumbersomes work with clones which then all must have original
repository added as a remote.

`check = False` could be the one needed for a 'publish' operation
where this data present locally is not yet published anywhere.

Tagging
~~~~~~~

We might like to tag files... TODO: think what to provide/use to
develop nice tags.

Ideas:

- a tag given a set of filename regexps

      [tag:anatomicals]
      files = .*\_anat\.nii\.gz
      tag = modality=anatomy

   or just

      [tag:anatomicals]
      files = .*\_anat\.nii\.gz
      tag = anatomy

   if it is just a tag (anatomy) without a field

 - (full)filename regexp with groups defining possibly multiple
   tag/value pairs

      [tag:modality]
      files = .*\_(?P<modality>\S*)\.nii\.gz
      translate = anat: T1     #  might need some translation dictionary?
                  dwi: DTI


Notes:
- metadata cane be added only to files under git-annex control so those
  directly committed

Design thoughts
===============

Data providers should provide a unified interface

DataProvider
~~~~~~~~~~~~

Common Parameters
- add_to_git  - what files to commit to git directly (should we leverage
   git-annex largefiles option somehow?)
- ignore      - what files to ignore

- get_items(version=None) - return a list of Files
- get_item_by_name
- get_item_by_md5
  - should those be additional interfaces?
  - what if multiple items fulfill (content is the same, e.g. empty, names differ,
    we better get the most appropriate in the name or don't give a damn?)
  - what if a collision????
- get_item_by_sha256
  - e.g. natively provided by 'Branch' provider for annexed files
    (what to do about git committed ones -- compute/keep info?)
- get_versions(min_version=None)
  provider-wide version (i.e. not per file).  E.g. S3
  provider can have multiple versions of files.
  Might be that it needs to return a DAG of versions i.e. a
  (version, [prev_version1, prev_version2, ...]) to represent e.g.
  history of a Git repo.  In most of the cases would be degenerate to just
  one prev version, in which case could just be (version, ).
  We would need to store that meta-information for future updates at least
  for the last version so we could 'grow' next ones on top.
- ? get_release_versions() -- by default identical to above... but might
  differ (update was, but no new official release (yet), so no release
  tag)
- get_version_metainformation() -- primarily conceived when thinking
  about monitoring other VCS repos... so should be information to be
  used for a new Git commit into this new repository

.. note:

    Keep in mind
    - Web DataProvider must have an option to request the content filename
      (addressing use case with redirects etc)
    - Some providers might have multiple URIs (mirrors) so right away
      assign them per each file...  As such they might be from
      different Hostings!


File
~~~~

what would be saved as a file.  Should know about itself... and origins!

- filename
- URIs  - list containing origins (e.g. URLs) on where to fetch it from.
          First provided by the
          original DataProvider, but then might be expanded using
          other DataProviders
          Q: Those might need to be not just URIs but some classes associated
          with original Hosting's, e.g. for the cases of authentication etc?
          or we would associate with a Hosting based on the URI?
  # combination of known fields should be stored/used to detect changes
  # Different data providers might rely on a different subset of below
  # to see if there was a change.  We should probably assume some
  # "correspondence"
- key   # was thinking about Branch as DataProvider -- those must be reused
- md5
- sha256
- mtime
- size

It will be the job of a DataProvider to initiate File with the
appropriate filename.

URI
~~~

-> URL(URI):  will be our first and main "target" but it could
              also be direct S3, etc.

a URI should be associated with an "Hosting" (many-to-one), so we could
e.g. provide authentication information per actual "Hosting" as the
entity.  But now we are getting back to DataProvider, which is the
Hosting, or actually also a part of it (since Hosting could serve
multiple Providers, e.g. openfmri -> providers per each dataset?)
But also Provider might use/point to multiple Hostings (e.g. mirrors
listed on nitp-2013).

Hosting
~~~~~~~

Each DataProvider would be a factory of File's.


Ideas to not forget
~~~~~~~~~~~~~~~~~~~

- Before carrying out some operation, remember the state of all
  (involved) branches, so it would be very easy later on to "cancel"
  the entire transaction through a set of 'git reset --hard' or
  'update-ref's.

  Keep log of the above!

- multiple data providers could be specified but there should be
  'primary' and 'complimentary' ones:

  - primary provider(s) define the layout/content
  - complimentary providers just provide references to additional
    locations where that data (uniquely identified via checksums etc)
    could be obtained, so we could add more data providing urls
  - Q: should all DataProvider's be able to serve as primary and complimentary?
  - most probably we should allow for an option to 'fail' or issue a
    warning in some cases
    - secondary provider doesn't carry a requested load/file
    - secondary provider provides some files not provided by the primary
      data provider

- at the end of the crawl operation, verify that all the files have all
  and only urls from the provided data providers

- allow to add/specify conventional git/annex clones as additional,
  conventional (non special) remotes to be added.

- allow to prepopulate URLs given e.g. perspective hosting on HTTP.
  This way whenever content gets published there -- all files would
  have appropriate URLs associated and would 'transcend' through the
  clones without requiring adding original remote.

Updates
=======

- must track updates and removals of the files
- must verify presence (add, remove) of the urls associated with the
  files given a list of data providers


Meta information
================

Since a while `git annex` provides a neat feature allowing to assign
tags to the files and later use e.g. `git annex view` to quickly
generate customized views of the repository.


Some cool related tools
=======================

https://github.com/scrapy/scrapely
  Pure Python (no DOM, lxml, etc) scraping of pages, "training" the
  scraper given a sample.  May be could be handy???
https://github.com/scrapy/slybot
  Brings together scrapy + scrapely to provide json-specs for
  spiders/items/etc
  Might be worth at least adopting spiders specs...?
  Has a neat slybot/validation/schemas.json  which validates the schematic 
