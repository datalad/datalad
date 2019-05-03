# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Create and update a dataset from a list of URLs.
"""

from collections import Mapping
from functools import partial
import logging
import os
import re
import string

from six import string_types
from six.moves.urllib.parse import urlparse

from datalad.dochelpers import exc_str
from datalad.log import log_progress, with_result_progress
from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.results import annexjson2result, get_status_dict
from datalad.interface.common_opts import nosave_opt
from datalad.support.exceptions import AnnexBatchCommandError
from datalad.support.network import get_url_filename
from datalad.support.path import split_ext
from datalad.support.s3 import get_versioned_url
from datalad.utils import (
    assure_list,
    unlink,
)

lgr = logging.getLogger("datalad.plugin.addurls")

__docformat__ = "restructuredtext"


class Formatter(string.Formatter):
    """Formatter that gives precedence to custom keys.

    The first positional argument to the `format` call should be a
    mapping whose keys are exposed as placeholders (e.g.,
    "{key1}.py").

    Parameters
    ----------
    idx_to_name : dict
        A mapping from a positional index to a key.  If not provided,
        "{N}" elements are not supported.
    missing : str, optional
        When column lookup results in an empty string, use this value in
        its place.
    """

    def __init__(self, idx_to_name=None, missing_value=None):
        self.idx_to_name = idx_to_name or {}
        self.missing = missing_value

    def format(self, format_string, *args, **kwargs):
        if not isinstance(args[0], Mapping):
            raise ValueError("First positional argument should be mapping")
        return super(Formatter, self).format(format_string, *args, **kwargs)

    def get_value(self, key, args, kwargs):
        """Look for key's value in `args[0]` mapping first.
        """
        # FIXME: This approach will fail for keys that contain "!" and
        # ":" because they'll be interpreted as formatting flags.
        data = args[0]

        name = key
        try:
            key_int = int(key)
        except ValueError:
            pass
        else:
            name = self.idx_to_name[key_int]

        try:
            value = data[name]
        except KeyError:
            return super(Formatter, self).get_value(
                key, args, kwargs)

        if self.missing is not None and isinstance(value, string_types):
            return value or self.missing
        return value

    def convert_field(self, value, conversion):
        if conversion == 'l':
            return str(value).lower()
        return super(Formatter, self).convert_field(value, conversion)


class RepFormatter(Formatter):
    """Extend Formatter to support a {_repindex} placeholder.
    """

    def __init__(self, *args, **kwargs):
        super(RepFormatter, self).__init__(*args, **kwargs)
        self.repeats = {}
        self.repindex = 0

    def format(self, *args, **kwargs):
        self.repindex = 0
        result = super(RepFormatter, self).format(*args, **kwargs)
        if result in self.repeats:
            self.repindex = self.repeats[result] + 1
            self.repeats[result] = self.repindex
            result = super(RepFormatter, self).format(*args, **kwargs)
        else:
            self.repeats[result] = 0
        return result

    def get_value(self, key, args, kwargs):
        args[0]["_repindex"] = self.repindex
        return super(RepFormatter, self).get_value(key, args, kwargs)


def clean_meta_args(args):
    """Process metadata arguments.

    Parameters
    ----------
    args : iterable of str
        Formatted metadata arguments for 'git-annex metadata --set'.

    Returns
    -------
    A dict mapping field names to values.
    """
    results = {}
    for arg in args:
        parts = [x.strip() for x in arg.split("=", 1)]
        if len(parts) == 2:
            if not parts[0]:
                raise ValueError("Empty field name")
            field, value = parts
        else:
            raise ValueError("meta argument isn't in 'field=value' format")

        if not value:
            # The `url_file` may have an empty value.
            continue
        results[field] = value
    return results


def get_subpaths(filename):
    """Convert "//" marker in `filename` to a list of subpaths.

    >>> from datalad.plugin.addurls import get_subpaths
    >>> get_subpaths("p1/p2//p3/p4//file")
    ('p1/p2/p3/p4/file', ['p1/p2', 'p1/p2/p3/p4'])

    Note: With Python 3, the subpaths could be generated with

        itertools.accumulate(filename.split("//")[:-1], os.path.join)

    Parameters
    ----------
    filename : str
        File name with "//" marking subpaths.

    Returns
    -------
    A tuple of the filename with any "//" collapsed to a single
    separator and a list of subpaths (str).
    """
    if "//" not in filename:
        return filename, []

    spaths = []
    for part in filename.split("//")[:-1]:
        path = os.path.join(*(spaths + [part]))
        spaths.append(path)
    return filename.replace("//", os.path.sep), spaths


def is_legal_metafield(name):
    """Test whether `name` is a valid metadata field.

    The set of permitted characters is taken from git-annex's
    MetaData.hs:legalField.
    """
    return bool(re.match(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*\Z", name))


def filter_legal_metafield(fields):
    """Remove illegal names from `fields`.

    Note: This is like `filter(is_legal_metafield, fields)` but the
    dropped values are logged.
    """
    legal = []
    for field in fields:
        if is_legal_metafield(field):
            legal.append(field)
        else:
            lgr.debug("%s is not a valid metadata field name; dropping",
                      field)
    return legal


def get_fmt_names(format_string):
    """Yield field names in `format_string`.
    """
    for _, name, _, _ in string.Formatter().parse(format_string):
        if name:
            yield name


def fmt_to_name(format_string, num_to_name):
    """Try to map a format string to a single name.

    Parameters
    ----------
    format_string : string
    num_to_name : dict
        A dictionary that maps from an integer to a column name.  This
        enables mapping the format string to an integer to a name.

    Returns
    -------
    A placeholder name if `format_string` consists of a single
    placeholder and no other text.  Otherwise, None is returned.
    """
    parsed = list(string.Formatter().parse(format_string))
    if len(parsed) != 1:
        # It's an empty string or there's more than one placeholder.
        return
    if parsed[0][0]:
        # Format string contains text before the placeholder.
        return

    name = parsed[0][1]
    if not name:
        # The field name is empty.
        return

    try:
        return num_to_name[int(name)]
    except (KeyError, ValueError):
        return name


def _read(stream, input_type):
    if input_type == "csv":
        import csv
        csvrows = csv.reader(stream)
        headers = next(csvrows)
        lgr.debug("Taking %s fields from first line as headers: %s",
                  len(headers), headers)
        idx_map = dict(enumerate(headers))
        rows = [dict(zip(headers, r)) for r in csvrows]
    elif input_type == "json":
        import json
        rows = json.load(stream)
        # For json input, we do not support indexing by position,
        # only names.
        idx_map = {}
    else:
        raise ValueError("input_type must be 'csv', 'json', or 'ext'")
    return rows, idx_map


def _format_filenames(format_fn, rows, row_infos):
    subpaths = set()
    for row, info in zip(rows, row_infos):
        filename = format_fn(row)
        filename, spaths = get_subpaths(filename)
        subpaths |= set(spaths)
        info["filename"] = filename
        info["subpath"] = spaths[-1] if spaths else None
    return subpaths


def get_file_parts(filename, prefix="name"):
    """Assign a name to various parts of a file.

    Parameters
    ----------
    filename : str
        A file name (no leading path is permitted).
    prefix : str
        Prefix to prepend to the key names.

    Returns
    -------
    A dict mapping each part to a value.
    """
    root, ext = split_ext(filename)
    root_py, ext_py = os.path.splitext(filename)

    return {prefix: filename,
            prefix + "_root": root,
            prefix + "_ext": ext,
            prefix + "_root_py": root_py,
            prefix + "_ext_py": ext_py}


def get_url_parts(url):
    """Assign a name to various parts of the URL.

    Parameters
    ----------
    url : str

    Returns
    -------
    A dict with keys `_url_hostname` and, for a path with N+1 parts,
    '_url0' through '_urlN' .  There is also a `_url_basename` key for
    the rightmost part of the path.
    """
    parsed = urlparse(url)
    if not parsed.netloc:
        return {}

    names = {"_url_hostname": parsed.netloc}

    path = parsed.path.strip("/")
    if not path:
        return names

    url_parts = path.split("/")
    for pidx, part in enumerate(url_parts):
        names["_url{}".format(pidx)] = part
    basename = url_parts[-1]
    names["_url_basename"] = basename
    names.update(get_file_parts(basename, prefix="_url_basename"))
    return names


def add_extra_filename_values(filename_format, rows, urls, dry_run):
    """Extend `rows` with values for special formatting fields.
    """
    file_fields = list(get_fmt_names(filename_format))
    if any(i.startswith("_url") for i in file_fields):
        for row, url in zip(rows, urls):
            row.update(get_url_parts(url))

    if any(i.startswith("_url_filename") for i in file_fields):
        if dry_run:  # Don't waste time making requests.
            dummy = get_file_parts("BASE.EXT", "_url_filename")
            for idx, row in enumerate(rows):
                row.update(
                    {k: v + str(idx) for k, v in dummy.items()})
        else:
            num_urls = len(urls)
            log_progress(lgr.info, "addurls_requestnames",
                         "Requesting file names for %d URLs", num_urls,
                         label="Requesting names", total=num_urls,
                         unit=" Files")
            for row, url in zip(rows, urls):
                # If we run into any issues here, we're just going to raise an
                # exception and then abort inside dlplugin.  It'd be good to
                # disentangle this from `extract` so that we could yield an
                # individual error, drop the row, and keep going.
                filename = get_url_filename(url)
                if filename:
                    row.update(get_file_parts(filename, "_url_filename"))
                else:
                    raise ValueError(
                        "{} does not contain a filename".format(url))
                log_progress(lgr.info, "addurls_requestnames",
                             "%s returned for %s", url, filename,
                             update=1, increment=True)
            log_progress(lgr.info, "addurls_requestnames",
                         "Finished requesting file names")


def extract(stream, input_type, url_format="{0}", filename_format="{1}",
            exclude_autometa=None, meta=None,
            dry_run=False, missing_value=None):
    """Extract and format information from `url_file`.

    Parameters
    ----------
    stream : file object
        Items used to construct the file names and URLs.
    input_type : {'csv', 'json'}

    All other parameters match those described in `AddUrls`.

    Returns
    -------
    A tuple where the first item is a list with a dict of extracted information
    for each row in `stream` and the second item is a set that contains all the
    subdataset paths.
    """
    meta = assure_list(meta)

    rows, colidx_to_name = _read(stream, input_type)

    fmt = Formatter(colidx_to_name, missing_value)  # For URL and meta
    format_url = partial(fmt.format, url_format)

    auto_meta_args = []
    if exclude_autometa not in ["*", ""]:
        urlcol = fmt_to_name(url_format, colidx_to_name)
        # TODO: Try to normalize invalid fields, checking for any
        # collisions.
        metacols = (c for c in sorted(rows[0].keys()) if c != urlcol)
        if exclude_autometa:
            metacols = (c for c in metacols
                        if not re.search(exclude_autometa, c))
        metacols = filter_legal_metafield(metacols)
        auto_meta_args = [c + "=" + "{" + c + "}" for c in metacols]

    # Unlike `filename_format` and `url_format`, `meta` is a list
    # because meta may be given multiple times on the command line.
    formats_meta = [partial(fmt.format, m) for m in meta + auto_meta_args]

    rows_with_url = []
    infos = []
    for row in rows:
        url = format_url(row)
        if not url or url == missing_value:
            continue  # pragma: no cover, peephole optimization
        rows_with_url.append(row)
        meta_args = clean_meta_args(fmt(row) for fmt in formats_meta)
        infos.append({"url": url, "meta_args": meta_args})

    n_dropped = len(rows) - len(rows_with_url)
    if n_dropped:
        lgr.warning("Dropped %d row(s) that had an empty URL", n_dropped)

    # Format the filename in a second pass so that we can provide
    # information about the formatted URLs.
    add_extra_filename_values(filename_format, rows_with_url,
                              [i["url"] for i in infos],
                              dry_run)

    # For the file name, we allow the _repindex special key.
    format_filename = partial(
        RepFormatter(colidx_to_name, missing_value).format,
        filename_format)
    subpaths = _format_filenames(format_filename, rows_with_url, infos)
    return infos, subpaths


@with_result_progress("Adding URLs")
def add_urls(rows, ifexists=None, options=None):
    """Call `git annex addurl` using information in `rows`.
    """
    for row in rows:
        filename_abs = row["filename_abs"]
        ds, filename = row["ds"], row["ds_filename"]
        lgr.debug("Adding metadata to %s in %s", filename, ds.path)

        if os.path.exists(filename_abs) or os.path.islink(filename_abs):
            if ifexists == "skip":
                yield get_status_dict(action="addurls",
                                      ds=ds,
                                      type="file",
                                      path=filename_abs,
                                      status="notneeded")
                continue
            elif ifexists == "overwrite":
                lgr.debug("Removing %s", filename_abs)
                unlink(filename_abs)
            else:
                lgr.debug("File %s already exists", filename_abs)

        try:
            out_json = ds.repo.add_url_to_file(filename, row["url"],
                                               batch=True, options=options)
        except AnnexBatchCommandError as exc:
            yield get_status_dict(action="addurls",
                                  ds=ds,
                                  type="file",
                                  path=filename_abs,
                                  message=exc_str(exc),
                                  status="error")
            continue

        # In the case of an error, the json object has file=None.
        if out_json["file"] is None:
            out_json["file"] = filename_abs
        yield annexjson2result(out_json, ds, action="addurls",
                               type="file", logger=lgr)


@with_result_progress("Adding metadata")
def add_meta(rows):
    """Call `git annex metadata --set` using information in `rows`.
    """
    from mock import patch

    for row in rows:
        ds, filename = row["ds"], row["ds_filename"]

        with patch.object(ds.repo, "always_commit", False):
            lgr.debug("Adding metadata to %s in %s", filename, ds.path)
            for a in ds.repo.set_metadata_(filename, add=row["meta_args"]):
                res = annexjson2result(a, ds, type="file", logger=lgr)
                # Don't show all added metadata for the file because that
                # could quickly flood the output.
                del res["message"]
                yield res


@build_doc
class Addurls(Interface):
    """Create and update a dataset from a list of URLs.

    *Format specification*

    Several arguments take format strings.  These are similar to normal Python
    format strings where the names from `URL-FILE` (column names for a CSV or
    properties for JSON) are available as placeholders.  If `URL-FILE` is a CSV
    file, a positional index can also be used (i.e., "{0}" for the first
    column).  Note that a placeholder cannot contain a ':' or '!'.

    In addition, the `FILENAME-FORMAT` arguments has a few special
    placeholders.

      - _repindex

        The constructed file names must be unique across all fields rows.  To
        avoid collisions, the special placeholder "_repindex" can be added to
        the formatter.  Its value will start at 0 and increment every time a
        file name repeats.

      - _url_hostname, _urlN, _url_basename*

        Various parts of the formatted URL are available.  Take
        "http://datalad.org/asciicast/seamless_nested_repos.sh" as an example.

        "datalad.org" is stored as "_url_hostname".  Components of the URL's
        path can be referenced as "_urlN".  "_url0" and "_url1" would map to
        "asciicast" and "seamless_nested_repos.sh", respectively.  The final
        part of the path is also available as "_url_basename".

        This name is broken down further.  "_url_basename_root" and
        "_url_basename_ext" provide access to the root name and extension.
        These values are similar to the result of os.path.splitext, but, in the
        case of multiple periods, the extension is identified using the same
        length heuristic that git-annex uses.  As a result, the extension of
        "file.tar.gz" would be ".tar.gz", not ".gz".  In addition, the fields
        "_url_basename_root_py" and "_url_basename_ext_py" provide access to
        the result of os.path.splitext.

      - _url_filename*

        These are similar to _url_basename* fields, but they are obtained with
        a server request.  This is useful if the file name is set in the
        Content-Disposition header.


    *Examples*

    Consider a file "avatars.csv" that contains::

        who,ext,link
        neurodebian,png,https://avatars3.githubusercontent.com/u/260793
        datalad,png,https://avatars1.githubusercontent.com/u/8927200

    To download each link into a file name composed of the 'who' and 'ext'
    fields, we could run::

      $ datalad addurls -d avatar_ds --fast avatars.csv '{link}' '{who}.{ext}'

    The `-d avatar_ds` is used to create a new dataset in "$PWD/avatar_ds".

    If we were already in a dataset and wanted to create a new subdataset in an
    "avatars" subdirectory, we could use "//" in the `FILENAME-FORMAT`
    argument::

      $ datalad addurls --fast avatars.csv '{link}' 'avatars//{who}.{ext}'

    .. note::

       For users familiar with 'git annex addurl': A large part of this
       plugin's functionality can be viewed as transforming data from
       `URL-FILE` into a "url filename" format that fed to 'git annex addurl
       --batch --with-files'.
    """

    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import EnsureChoice, EnsureNone, EnsureStr
    from datalad.support.param import Parameter

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""Add the URLs to this dataset (or possibly subdatasets of
            this dataset).  An empty or non-existent directory is passed to
            create a new dataset.  New subdatasets can be specified with
            `FILENAME-FORMAT`.""",
            constraints=EnsureDataset() | EnsureNone()),
        urlfile=Parameter(
            args=("urlfile",),
            metavar="URL-FILE",
            doc="""A file that contains URLs or information that can be used to
            construct URLs.  Depending on the value of --input-type, this
            should be a CSV file (with a header as the first row) or a JSON
            file (structured as a list of objects with string values)."""),
        urlformat=Parameter(
            args=("urlformat",),
            metavar="URL-FORMAT",
            doc="""A format string that specifies the URL for each entry.  See
            the 'Format Specification' section above."""),
        filenameformat=Parameter(
            args=("filenameformat",),
            metavar="FILENAME-FORMAT",
            doc="""Like `URL-FORMAT`, but this format string specifies the file
            to which the URL's content will be downloaded.  The file name may
            contain directories.  The separator "//" can be used to indicate
            that the left-side directory should be created as a new subdataset.
            See the 'Format Specification' section above."""),
        input_type=Parameter(
            args=("-t", "--input-type"),
            metavar="TYPE",
            doc="""Whether `URL-FILE` should be considered a CSV file or a JSON
            file.  The default value, "ext", means to consider `URL-FILE` as a
            JSON file if it ends with ".json".  Otherwise, treat it as a CSV
            file.""",
            constraints=EnsureChoice("ext", "csv", "json")),
        exclude_autometa=Parameter(
            args=("-x", "--exclude_autometa"),
            metavar="REGEXP",
            doc="""By default, metadata field=value pairs are constructed with
            each column in `URL-FILE`, excluding any single column that is
            specified via `URL-FORMAT`.  This argument can be used to exclude
            columns that match a regular expression.  If set to '*' or an empty
            string, automatic metadata extraction is disabled completely.  This
            argument does not affect metadata set explicitly with --meta."""),
        meta=Parameter(
            args=("-m", "--meta",),
            metavar="FORMAT",
            action="append",
            doc="""A format string that specifies metadata.  It should be
            structured as "<field>=<value>".  As an example, "location={3}"
            would mean that the value for the "location" metadata field should
            be set the value of the fourth column.  This option can be given
            multiple times."""),
        message=Parameter(
            args=("--message",),
            metavar="MESSAGE",
            doc="""Use this message when committing the URL additions.""",
            constraints=EnsureNone() | EnsureStr()),
        dry_run=Parameter(
            args=("-n", "--dry-run"),
            action="store_true",
            doc="""Report which URLs would be downloaded to which files and
            then exit."""),
        fast=Parameter(
            args=("--fast",),
            action="store_true",
            doc="""If True, add the URLs, but don't download their content.
            Underneath, this passes the --fast flag to `git annex addurl`."""),
        ifexists=Parameter(
            args=("--ifexists",),
            doc="""What to do if a constructed file name already exists.  The
            default behavior is to proceed with the `git annex addurl`, which
            will fail if the file size has changed.  If set to 'overwrite',
            remove the old file before adding the new one.  If set to 'skip',
            do not add the new file.""",
            constraints=EnsureChoice(None, "overwrite", "skip")),
        missing_value=Parameter(
            args=("--missing-value",),
            metavar="VALUE",
            doc="""When an empty string is encountered, use this value
            instead.""",
            constraints=EnsureNone() | EnsureStr()),
        save=nosave_opt,
        version_urls=Parameter(
            args=("--version-urls",),
            action="store_true",
            doc="""Try to add a version ID to the URL. This currently only has
            an effect on URLs for AWS S3 buckets."""),
    )

    @staticmethod
    @datasetmethod(name='addurls')
    @eval_results
    def __call__(dataset, urlfile, urlformat, filenameformat,
                 input_type="ext", exclude_autometa=None, meta=None,
                 message=None, dry_run=False, fast=False, ifexists=None,
                 missing_value=None, save=True, version_urls=False):
        # Temporarily work around gh-2269.
        url_file = urlfile
        url_format, filename_format = urlformat, filenameformat

        from requests.exceptions import RequestException

        from datalad.distribution.dataset import Dataset, require_dataset
        from datalad.interface.results import get_status_dict
        from datalad.support.annexrepo import AnnexRepo

        lgr = logging.getLogger("datalad.plugin.addurls")

        dataset = require_dataset(dataset, check_installed=False)
        if dataset.repo and not isinstance(dataset.repo, AnnexRepo):
            yield get_status_dict(action="addurls",
                                  ds=dataset,
                                  status="error",
                                  message="not an annex repo")
            return

        if input_type == "ext":
            extension = os.path.splitext(url_file)[1]
            input_type = "json" if extension == ".json" else "csv"

        with open(url_file) as fd:
            try:
                rows, subpaths = extract(fd, input_type,
                                         url_format, filename_format,
                                         exclude_autometa, meta,
                                         dry_run,
                                         missing_value)
            except (ValueError, RequestException) as exc:
                yield get_status_dict(action="addurls",
                                      ds=dataset,
                                      status="error",
                                      message=exc_str(exc))
                return

        if len(rows) != len(set(row["filename"] for row in rows)):
            yield get_status_dict(action="addurls",
                                  ds=dataset,
                                  status="error",
                                  message=("There are file name collisions; "
                                           "consider using {_repindex}"))
            return

        if dry_run:
            for subpath in subpaths:
                lgr.info("Would create a subdataset at %s", subpath)
            for row in rows:
                lgr.info("Would download %s to %s",
                         row["url"],
                         os.path.join(dataset.path, row["filename"]))
                lgr.info("Metadata: %s",
                         sorted(u"{}={}".format(k, v)
                                for k, v in row["meta_args"].items()))
            yield get_status_dict(action="addurls",
                                  ds=dataset,
                                  status="ok",
                                  message="dry-run finished")
            return

        if not dataset.repo:
            # Populate a new dataset with the URLs.
            for r in dataset.create(result_xfm=None,
                                    return_type='generator'):
                yield r

        annex_options = ["--fast"] if fast else []

        for spath in subpaths:
            if os.path.exists(os.path.join(dataset.path, spath)):
                lgr.warning(
                    "Not creating subdataset at existing path: %s",
                    spath)
            else:
                for r in dataset.create(spath, result_xfm=None,
                                        return_type='generator'):
                    yield r

        for row in rows:
            # Add additional information that we'll need for various
            # operations.
            filename_abs = os.path.join(dataset.path, row["filename"])
            if row["subpath"]:
                ds_current = Dataset(os.path.join(dataset.path,
                                                  row["subpath"]))
                ds_filename = os.path.relpath(filename_abs, ds_current.path)
            else:
                ds_current = dataset
                ds_filename = row["filename"]
            row.update({"filename_abs": filename_abs,
                        "ds": ds_current,
                        "ds_filename": ds_filename})

        if version_urls:
            num_urls = len(rows)
            log_progress(lgr.info, "addurls_versionurls",
                         "Versioning %d URLs", num_urls,
                         label="Versioning URLs",
                         total=num_urls, unit=" URLs")
            for row in rows:
                url = row["url"]
                try:
                    row["url"] = get_versioned_url(url)
                except (ValueError, NotImplementedError) as exc:
                    # We don't expect this to happen because get_versioned_url
                    # should return the original URL if it isn't an S3 bucket.
                    # It only raises exceptions if it doesn't know how to
                    # handle the scheme for what looks like an S3 bucket.
                    lgr.warning("error getting version of %s: %s",
                                row["url"], exc_str(exc))
                log_progress(lgr.info, "addurls_versionurls",
                             "Versioned result for %s: %s", url, row["url"],
                             update=1, increment=True)
            log_progress(lgr.info, "addurls_versionurls", "Finished versioning URLs")

        files_to_add = set()
        for r in add_urls(rows, ifexists=ifexists, options=annex_options):
            if r["status"] == "ok":
                files_to_add.add(r["path"])
            yield r

            msg = message or """\
[DATALAD] add files from URLs

url_file='{}'
url_format='{}'
filename_format='{}'""".format(url_file, url_format, filename_format)

        if files_to_add:
            for r in dataset.add(files_to_add, save=False):
                yield r

            meta_rows = [r for r in rows if r["filename_abs"] in files_to_add]
            for r in add_meta(meta_rows):
                yield r

            # Save here rather than the add call above to trigger a metadata
            # commit on the git-annex branch.
            if save:
                for r in dataset.save(message=msg, recursive=True):
                    yield r


__datalad_plugin__ = Addurls
