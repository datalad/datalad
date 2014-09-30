Config file format
==================

Includes
--------

:mod:`~datalad.config` enhances class:`~ConfigParser.SafeConfigParser`
to also support includes.  It makes it possible to specify within the
`INCLUDES` section of the config file which other config file should
be considered before or after a currently read config file::

    [INCLUDES]
    before = defaults.cfg
    after = customizations.cfg

    [DEFAULTS]
    ....

Sections
--------

Download section
~~~~~~~~~~~~~~~~

It is the only type of a section at this point.  It specifies a single
resource which crawl/monitor and fetch specified content to be
deposited into the git/git-annex repository.  Following fields are
known and could either be specified in the specific section or in
`DEFAULT` section to be reused across different sections

mode
  Could be `download`, `fast` or `relaxed`. In `download` mode files
  are downloaded, and added to the git-annex, thus based on a checksum
  backend.  `fast` and `relaxed` modes correspond to the modes of `git
  annex addurl`
incoming
  Path to the `incoming` repository -- where everything gets initially
  imported, e.g. original archives.  If no archives to be extracted,
  it usually then matches with `public`.  Original idea for such a
  separation was to cover the cases where incoming materials
  (archives) might contain some non-distributable materials which
  should be stripped before being placed into `public` repository
public
  Path to the `public` repository which is the target repository to be
  shared
description
  Textual description to be placed under :file:`.git/description`
include_href
  Regular expression to specify which URLs, pointed to by HTML `<A>`
  should be considered to be added to the repository
include_href_a
  Regular expression to specify which links with matching text should
  be considered
exclude_href, exclude_href_a
  Similar setups to specify which ones to exclude (e.g. if `include_href=.*`)
recurse
  Regular expression to specify which URLs to consider for further
  traversal while crawling the website

TODO. Some additional documentation is currently within
:meth:`datalad.config.EnhancedConfigParser.get_default`
