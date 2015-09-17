# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import calendar
import email.utils
import gzip
import os
import re
import shutil
import time

from six import string_types
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, urlunparse
from six.moves.urllib.error import URLError
from six.moves import StringIO

from bs4 import BeautifulSoup

import logging
lgr = logging.getLogger('datalad.network')

from joblib import Memory
memory = Memory(cachedir="/tmp/datalad", verbose=1)

def get_response_deposition_filename(response_info):
    if 'Content-Disposition' in response_info:
        # If the response has Content-Disposition, try to get filename from it
        cd = dict(map(
            lambda x: x.strip().split('=') if '=' in x else (x.strip(),''),
            response_info['Content-Disposition'].split(';')))
        if 'filename' in cd:
            filename = cd['filename'].strip("\"'")
            return filename
    return None

def get_url_deposition_filename(url):
    request = Request(url)
    r = retry_urlopen(request)
    try:
        return get_response_deposition_filename(r.info())
    finally:
        r.close()

def get_url_straight_filename(url):
    return os.path.basename(urlunquote(urlsplit(url).path))

def get_url_response_stamp(url, response_info):
    size, mtime = None, None
    if 'Content-length' in response_info:
        size = int(response_info['Content-length'])
    if 'Last-modified' in response_info:
        mtime = calendar.timegm(email.utils.parsedate(
            response_info['Last-modified']))
    return dict(size=size, mtime=mtime, url=url)

def __download(url, filename=None, filename_only=False):
    # http://stackoverflow.com/questions/862173/how-to-download-a-file-using-python-in-a-smarter-way
    request = Request(url)
    request.add_header('Accept-encoding', 'gzip,deflate')
    r = urlopen(request)
    try:
        filename = filename or getFileName(url, r)
        if not filename_only:
            with open(filename, 'wb') as f:
                if r.info().get('Content-Encoding') == 'gzip':
                    buf = StringIO(r.read())
                    src = gzip.GzipFile(fileobj=buf)
                else:
                    src = r
                shutil.copyfileobj(src, f)
    finally:
        r.close()
    return filename

def retry_urlopen(url, retries=3):
    for t in range(retries):
        try:
            return urlopen(url)
        except URLError as e:
            lgr.warn("Received exception while reading %s: %s" % (url, e))
            if t == retries - 1:
                # if we have reached allowed number of retries -- reraise
                raise


# yoh: I haven't found a quick way to enable/disable memory. caching at runtime,
# thus implementing simple decorators
def _fetch_page(url, retries=3):
    lgr.debug("Fetching %s" % url)
    openurl = retry_urlopen(url, retries=retries)
    for t in range(retries):
        try:
            page = openurl.read()
            break
        except URLError as e:
            lgr.warn("Received exception while reading %s: %s" % (url, e))
            if t == retries - 1:
                # if we have reached allowed number of retries -- reraise
                raise
    lgr.info("Fetched %d bytes page from %s" % (len(page), url))
    return page

def fetch_page(url, retries=3, cache=False):
    if cache:
        return memory.eval(_fetch_page, url, retries=retries)
    else:
        return _fetch_page(url, retries=retries)

def is_url_quoted(url):
    """Return either URL looks being already quoted
    """
    try:
        url_ = urlunquote(url)
        return url != url_
    except:  # problem with unquoting -- then it must be wasn't quoted (correctly)
        return False


def _parse_urls(page):
    lgr.debug("Parsing out urls")
    soup = BeautifulSoup(page, "html.parser")
    urls = []
    for link in soup.findAll('a'):
        href = link.get('href')
        if not href:
            # skip empties
            continue
        # we better bring it to canonical quoted form for consistency
        rec = urlsplit(href)
        path_quoted = urlquote(rec.path) if not is_url_quoted(rec.path) else rec.path
        href = urlunsplit((rec.scheme, rec.netloc, path_quoted,
                           rec.query, rec.fragment))
        urls.append((href, link.text, link))
    return urls

def parse_urls(page, cache=False):
    if False:  # cache:
        # disabled until bs4 addresses Pickling issue
        # https://bugs.launchpad.net/beautifulsoup/+bug/1231545
        return memory.eval(_parse_urls, page)
    else:
        return _parse_urls(page)

def same_website(url_rec, u_rec):
    """Decide either a link leads to external site

    Parameters
    ----------
    url_rec: ParseResult
      record for original url
    u_rec: ParseResult
      record for new url
    """
    if isinstance(url_rec, string_types):
        url_rec = urlparse(url_rec)
    if isinstance(u_rec, string_types):
        u_rec = urlparse(u_rec)
    return (url_rec.netloc == u_rec.netloc)
    # todo: collect more of sample cases.
    # disabled below check while working on ratholeradio, since links
    # could go to the parent and that is ok.  Figure out when it was
    # desired not to go to the parent -- we might need explicit option
    # and u_rec.path.startswith(url_rec.path)):

def dlurljoin(u_path, url):
    url_rec = urlparse(url)  # probably duplicating parsing :-/ TODO
    if url_rec.scheme:
        # independent full url, so just return it
        return url
    if u_path.endswith('/'):  # should here be also a scheme use?
        if url.startswith('/'): # jump to the root
            u_path_rec = urlparse(u_path)
            return urljoin(urlunparse((u_path_rec.scheme, u_path_rec.netloc, '','','','')), url)
        else:
            return os.path.join(u_path, url)
    # TODO: recall where all this dirname came from and bring into the test
    return urljoin(os.path.dirname(u_path) + '/', url)


def collect_urls(url, recurse=None, hot_cache=None, cache=False, memo=None):
    """Collects urls starting from url

    Parameters
    ----------
    recurse : string
      Regular expression to decide what to recurse into

    Returns
    -------
    list of (url, label, bs4.element)
    """
    page = (hot_cache and hot_cache.get(url, None)) or fetch_page(url, cache=cache)
    if hot_cache is not None:
        hot_cache[url] = page

    if recurse:
        if memo is None:
            memo = set()
        if url in memo:
            lgr.debug("Not considering %s since was analyzed before", url)
            return []
        memo.add(url)

    url_rec = urlparse(url)
    #
    # Parse out all URLs, as a tuple (url, a(text))
    urls_all = parse_urls(page, cache=cache)

    # Now we need to dump or recurse into some of them, e.g. for
    # directories etc
    urls = []
    if recurse:
        recurse_re = re.compile(recurse)

    lgr.debug("Got %d urls from %s", len(urls_all), url)

    for iurl, url_ in enumerate(urls_all):
        lgr.log(3, "#%d url=%s", iurl+1, url_)

        # separate tuple out
        u, a, l = url_
        recurse_match = recurse and recurse_re.search(u)
        u_rec = urlparse(u)
        u_path = u_rec.path
        u_is_directory = u_path.endswith('/')

        # join function to use
        # originally was just os.path.join but it would not be correct
        if u_is_directory or recurse_match:     # must be a directory or smth we were told to recurse into
            if u in ('../', './'):
                # TODO -- might be a full URL pointing to "Parent Directory"
                lgr.log(8, "Skipping %s -- we are not going to parents" % u)
                continue
            if not recurse:
                lgr.log(8, "Skipping %s since no recursion" % u)
                continue
            if recurse_match:
                # then we should fetch the one as well

                u_full = urljoin(url, u)
                if u_full in memo:
                    lgr.debug("Not considering %s for recursion since was analyzed before", u_full)
                    continue
                if u_rec.scheme:
                    if not same_website(url_rec, u_rec):
                        lgr.log(9, "Skipping %s since it jumps to another site from original %s" % (u, url))
                        #raise NotImplementedError("Cannot jump to other websites yet")
                        continue
                    # so we are staying on current website -- let it go
                lgr.debug("Recursing into %s, full: %s" % (u, u_full))
                new_urls = collect_urls(
                    u_full, recurse=recurse, hot_cache=hot_cache, cache=cache,
                    memo=memo)
                new_fullurls = [(dlurljoin(u_path, url__[0]),) + url__[1:]
                                 for url__ in new_urls]
                # and add to their "hrefs" appropriate prefix
                lgr.log(4, "Adding %d urls collected from %s" % (len(new_fullurls), u_full))
                urls.extend(new_fullurls)
                ## import pydb; pydb.debugger()
                ## i = 1
            else:
                lgr.log(8, "Skipping %s since doesn't match recurse" % u)
        else:
            lgr.log(4, "Adding %s", url_)
            urls.append(url_)

    lgr.debug("Considering %d out of %d urls from %s"
              % (len(urls), len(urls_all), url))

    return urls


def filter_urls(urls,
                include_href=None,
                exclude_href=None,
                include_href_a=None,
                exclude_href_a=None):

    if (not include_href) and not (include_href_a):
        include_href = '.*'               # include all

    # First do all includes explicitly and then excludes
    return [(url, a, l)
             for url, a, l in urls
                if url
                   and
                   ((include_href and re.search(include_href, url))
                     or (include_href_a and re.search(include_href_a, a))) \
                   and not
                   ((exclude_href and re.search(exclude_href, url))
                     or (exclude_href_a and re.search(exclude_href_a, a)))]

# TODO: RF move db_incoming and modes logic outside?
def download_url_to_incoming(url, incoming, subdir='', db_incoming=None, dry_run=False,
                 add_mode='download',
                 use_content_name=False,
                 use_redirected_name=True,
                 force_download=False):
    downloaded, updated, downloaded_size = False, False, 0
    # so we could check and remove it to keep it clean
    temp_full_filename = None

    if db_incoming is None:
        db_incoming = {}

    # unquote path's portion of url first
    url_filename = get_url_straight_filename(url)

    class ReturnSooner(Exception):
        pass

    try:  # might RF -- this is just to not repeat the same return
        if dry_run or add_mode == 'relaxed':
            # we can only try to deduce from the url...
            # TODO: now that there is use_content_name  -- make dry_run run smarter and more detailed
            #       just assume things haven't changed on the remote end and keep going without introducing
            #       any factual changes
            filename = url_filename
            repo_filename = os.path.join(subdir, filename)
            full_filename = os.path.join(incoming, repo_filename)
            # and not really do much
            if dry_run:
                lgr.debug("Nothing else could be done for download in dry mode")
                raise ReturnSooner
            elif add_mode == 'relaxed':
                if os.path.lexists(full_filename):
                    lgr.debug("File exists - nothing todo in 'relaxed' mode")
                    raise ReturnSooner
                if repo_filename in db_incoming:
                    lgr.debug("File found in db_incoming and doesn't exists - assuming was rm'ed")
                else:
                    lgr.debug("File was not found in db_incoming and doesn't exists. Marking updated")
                    db_incoming[repo_filename] = dict(url=url)
                    updated = True
                raise ReturnSooner
            else:
                raise RuntimeError("Should not get here")

        # TODO: add mode alike to 'relaxed' where we would not
        # care about content-deposition filename
        # http://stackoverflow.com/questions/862173/how-to-download-a-file-using-python-in-a-smarter-way
        request = Request(url)

        # No traffic compression since we do not know how to identify
        # exactly either it has to be decompressed
        # request.add_header('Accept-encoding', 'gzip,deflate')
        #
        # TODO: think about stamping etc -- we seems to be redoing
        # what git-annex does for us already... not really
        r = retry_urlopen(request)
        try:
            r_info = r.info()

            r_stamp = get_url_response_stamp(url, r_info)
            if use_redirected_name and url != r.url:
                # We were redirected (?) and might like to use actual url_filename
                # from the redirected URL
                # TODO: expose option
                url_filename = get_url_straight_filename(r.url)

            if use_content_name:
                filename = get_response_deposition_filename(r_info) or url_filename
            else:
                filename = url_filename

            repo_filename = os.path.join(subdir, filename)
            full_filename = os.path.join(incoming, repo_filename)

            if r_stamp['size']:
                lgr.debug("File %s is of size %d" % (repo_filename, r_stamp['size']))

            if url_filename != filename:
                lgr.debug("Filename in url %s differs from the load %s" % (url_filename, filename))

            # So we have filename -- time to figure out either we need to re-download it

            # db_incoming might maintain information even if file is not present, e.g.
            # if originally we haven't kept originals
            download = force_download

            def _compare_stamps(ofs, nfs, msg):
                """ofs -- old stamps, nfs -- new ones
                """
                download = False
                for k in ofs.keys():
                    n, o = nfs[k], ofs[k]
                    if n:
                        if o != n:
                            lgr.debug("Response %s %s differs from %s %s -- download"
                                      % (k, n, msg, o))
                            download = True
                return download

            if repo_filename in db_incoming:
                # if it is listed and has no stamps?
                # no -- it should have stamps -- we will place them there if none
                # was provided in HTML response. and we will redownload only
                # if any of those returned in HTTP header non-None and differ.
                # Otherwise we would assume that we have it
                # TODO: think if it is not too fragile
                download |= _compare_stamps(db_incoming.get(repo_filename),
                                            r_stamp, "previous")
                if not download:
                    lgr.debug("Stamps seems to be the same as before")

            elif os.path.exists(full_filename):
                lgr.debug("File %s already exists under %s but no known stamps for it"
                          % (repo_filename, full_filename))

                # Verify time stamps etc
                # TODO: IF IT IS UNDER git-annex -- we can't do this
                file_stat = os.stat(full_filename)
                ex_stamp = dict(size=file_stat.st_size,
                                mtime=file_stat.st_mtime)

                download |= _compare_stamps(ex_stamp, r_stamp, "file stats")

            if not (repo_filename in db_incoming) and not os.path.exists(full_filename):
                lgr.debug("File %s is not known and doesn't exist" % repo_filename)
                download = True

            mtime = r_stamp['mtime']
            size = r_stamp['size']

            # might be too early to state -- what if download fails?
            db_incoming[repo_filename] = dict(mtime=mtime, size=size, url=url)

            if add_mode in ['fast', 'relaxed']:
                if download:
                    lgr.debug("%r mode: not downloading but marking updated" % add_mode)
                updated = download
                raise ReturnSooner

            if not download:
                lgr.debug("Not downloading for the reasons above stated")
                raise ReturnSooner

            lgr.info("Need to download file %s under %s" % (repo_filename, incoming))

            if os.path.exists(full_filename):
                lgr.debug("Removing previously existing file")
                # TODO

            # actual download -- quite plain -- may be worth to offload to
            # wget or curl for now?
            temp_full_filename = full_filename + '.download'

            if os.path.exists(temp_full_filename):
                raise RuntimeError("File %s should not be there yet" % temp_full_filename)

            try:
                # TODO -- download to .downloachad temp file and rename upon success
                # TODO -- think either we should download here at all or just leave it
                #         up to git-annex to do... atm we allow for mode 'rm' so it
                #         might not be possible since it would not be fetched first by annex
                # we might need the directory
                full_filename_dir = os.path.dirname(temp_full_filename)
                if not os.path.exists(full_filename_dir):
                    os.makedirs(full_filename_dir)

                # TODO:  avoid manual download -- delegate to wget or aria2c.
                #  I don't think we are winning much from reusing original
                #  request, and would need to deal with aborted transfers etc
                #  Also then we wouldn't need to drag that 'r' around which was
                #  originally used only to get target filename and related "stamp"
                with open(temp_full_filename, 'wb') as f:
                    # No magical decompression for now
                    if False: #r.info().get('Content-Encoding') == 'gzip':
                        buf = StringIO( r.read())
                        src = gzip.GzipFile(fileobj=buf)
                    else:
                        src = r
                    shutil.copyfileobj(src, f)
                    downloaded = True
                downloaded_size = os.stat(temp_full_filename).st_size

            except Exception as e:
                lgr.error("Failed to download: %s" % e)
                if os.path.exists(temp_full_filename):
                    lgr.info("Removing %s" % temp_full_filename)
                    os.unlink(temp_full_filename)
                raise

            if mtime:
                lgr.debug("Setting downloaded file's mtime to %s obtained from HTTP header"
                          % r_stamp['mtime'])
                os.utime(temp_full_filename, (time.time(), mtime))

            # Get stats and check on success
            # TODO: may be some would have MD5SUMS associated?
            updated = True

            # get mtime so we could update entry for our file
            file_stat = os.stat(temp_full_filename)
            new_mtime = file_stat.st_mtime
            new_size = file_stat.st_size

            if mtime and (new_mtime != mtime):
                lgr.debug("Set mtime differs for some reason.  Got %s (%s) while it should have been %s (%s)"
                          % (new_mtime, time.gmtime(new_mtime),
                             mtime, time.gmtime(mtime)))
                updated = False

            if size and (new_size != size):
                lgr.debug("Downloaded file differs in size.  Got %d while it should have been %d"
                          % (new_size, size))
                updated = False

            if updated:
                # TODO: we might like to git annex drop previously existed file etc
                os.rename(temp_full_filename, full_filename)

            else:
                pass
        finally:
            r.close()
            if temp_full_filename and os.path.exists(temp_full_filename):
                lgr.debug("Removing left-over %s of size %d"
                          % (temp_full_filename, os.stat(temp_full_filename).st_size))
                os.unlink(temp_full_filename)

    except ReturnSooner:
        # We have handled things already, just need to return
        pass

    return repo_filename, downloaded, updated, downloaded_size

