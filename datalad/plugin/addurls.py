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
    """Prepare formatted metadata arguments to be passed to git-annex.

    Parameters
    ----------
    args : iterable of str
        Formatted metadata arguments for 'git-annex metadata --set'.

    Returns
    -------
    Generator that yields processed arguments (str).
    """
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

        yield field + "=" + value


def get_subpaths(filename):
    """Convert "//" marker in `filename` to a list of subpaths.

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


def get_url_names(url):
    """Assign a name to each part of a URL's path.

    Parameters
    ----------
    url : str

    Returns
    -------
    A dict with keys '_url0' through '_urlN' for a path with N+1
    components.  There is also a `_url_basename` for the rightmost
    entry.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return {}

    url_parts = path.split("/")
    names = {}
    for pidx, part in enumerate(url_parts):
        names["_url{}".format(pidx)] = part
    names["_url_basename"] = url_parts[-1]
    return names


def extract(stream, input_type, filename_format, url_format,
            exclude_autometa, meta, missing_value):
    """Extract and format information from `url_file`.

    Parameters
    ----------
    stream : file object
        Items used to construct the file names and URLs.

    All other parameters match those described in `dlplugin`.

    Returns
    -------
    A tuple where the first item is a list with a dict of extracted information
    for each row in `stream` and the second item is a set that contains all the
    subdataset paths.
    """
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

    infos = []
    for row in rows:
        meta_args = list(clean_meta_args(fmt(row) for fmt in formats_meta))
        infos.append({"url": format_url(row),
                      "meta_args": meta_args})

    # Format the filename in a second pass so that we can provide
    # information about the formatted URLs.
    if any(i.startswith("_url") for i in get_fmt_names(filename_format)):
        for row, info in zip(rows, infos):
            row.update(get_url_names(info["url"]))

    # For the file name, we allow the _repindex special key.
    format_filename = partial(
        RepFormatter(colidx_to_name, missing_value).format,
        filename_format)
    subpaths = _format_filenames(format_filename, rows, infos)
    return infos, subpaths


def dlplugin(dataset=None, url_file=None, input_type="ext",
             url_format="{0}", filename_format="{1}",
             exclude_autometa=None, meta=None,
             message=None, dry_run=False, fast=False,
             ifexists=None, missing_value=None):
    """Create and update a dataset from a list of URLs.

    Parameters
    ----------
    dataset : Dataset
        Add the URLs to this dataset (or possibly subdatasets of this
        dataset).  An empty or non-existent directory is passed to
        create a new dataset.  New subdatasets can be specified with
        `filename_format`.
    url_file : str
        A file that contains URLs or information that can be used to
        construct URLs.  Depending on the value of `input_type`, this
        should be a CSV file (with a header as the first row) or a
        JSON file (structured as a list of objects with string
        values).
    input_type : {"ext", "csv", "json"}, optional
        Whether `url_file` should be considered a CSV file or a JSON
        file.  The default value, "ext", means to consider `url_file`
        as a JSON file if it ends with ".json".  Otherwise, treat it
        as a CSV file.
    url_format : str, optional
        A format string that specifies the URL for each entry.  This
        value is similar to a normal Python format string where the
        names from `url_file` (column names for a CSV or properties
        for JSON) are available as placeholders.  If `url_file` is a
        CSV file, a positional index can also be used (i.e., "{0}" for
        the first column).  Note that a placeholder cannot contain a
        ':' or '!'.
    filename_format : str, optional
        Like `url_format`, but this format string specifies the file to
        which the URL's content will be downloaded.  The file name may
        contain directories.  The separator "//" can be used to indicate
        that the left-side directory should be created as a new
        subdataset.

        In addition to the placeholders described in `url_format`, there
        are a few special placeholders.

          - _repindex

            The constructed file names must be unique across all fields
            rows.  To avoid collisions, the special placeholder
            "_repindex" can be added to the formatter.  Its value will
            start at 0 and increment every time a file name repeats.

          - _urlN and _url_basename

            Each part of the formatted URL is available.  For example,
            in "http://datalad.org/for/git-users", "_url0" and "_url1"
            would map to "for" and "git-users", respectively.

            The final part is also available as "_url_basename".
    exclude_autometa : str, optional
        By default, metadata field=value pairs are constructed with each
        column in `url_file`, excluding any single column that is
        specified via `url_format`.  This argument can be used to
        exclude columns that match a regular expression.  If set to '*'
        or an empty string, automatic metadata extraction is disabled
        completely.  This argument does not affect metadata set
        explicitly with the `meta` argument.
    meta : str, optional
        A format string that specifies metadata.  It should be
        structured as "<field>=<value>".  The same placeholders from
        `url_format` can be used.  As an example, "location={3}" would
        mean that the value for the "location" metadata field should be
        set the value of the fourth column.  This option can be given
        multiple times.
    message : str, optional
        Use this message when committing the URL additions.
    dry_run : bool, optional
        Report which URLs would be downloaded to which files and then
        exit.
    fast : bool, optional
        If True, add the URLs, but don't download their content.
        Underneath, this passes the --fast flag to `git annex addurl`.
    ifexists : {None, 'overwrite', 'skip'}
        What to do if a constructed file name already exists.  The
        default (None) behavior to proceed with the `git annex addurl`,
        which will fail if the file size has changed.  If set to
        'overwrite', remove the old file before adding the new one.  If
        set to 'skip', do not add the new file.
    missing_value : str, optional
        When an empty string is encountered, use this value instead.

    Examples
    --------
    Consider a file "avatars.csv" that contains

        who,ext,link
        neurodebian,png,https://avatars3.githubusercontent.com/u/260793
        datalad,png,https://avatars1.githubusercontent.com/u/8927200

    To download each link into a file name composed of the 'who' and
    'ext' fields, we could run

        $ datalad plugin -d avatar_ds addurls url_file=avatars.csv
          url_format='{link}' filename_format='{who}.{ext}' fast=True

    The '-d avatar_ds' is used to create a new dataset in
    "$PWD/avatar_ds".

    If we were already in a dataset and wanted to create a new
    subdataset in an "avatars" subdirectory, we could use "//" in the
    `filename_format` argument:

        $ datalad plugin addurls url_file=avatars.csv
          url_format='{link}' filename_format='avatars//{who}.{ext}'
          fast=True

    Note
    ----
    For users familiar with 'git annex addurl': A large part of this
    plugin's functionality can be viewed as transforming data from
    `url_file` into a "url filename" format that fed to 'git annex
    addurl --batch --with-files'.
    """
    import logging
    import os

    from datalad.distribution.add import Add
    from datalad.distribution.create import Create
    from datalad.distribution.dataset import Dataset
    from datalad.interface.results import get_status_dict
    import datalad.plugin.addurls as me
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.exceptions import AnnexBatchCommandError
    from datalad.utils import assure_list
    from datalad.ui import ui

    lgr = logging.getLogger("datalad.plugin.addurls")

    meta = assure_list(meta)

    if url_file is None:
        # `url_file` is not a required argument in `dlplugin` because
        # the argument before it, `dataset`, needs to be optional to
        # support the creation of new datasets.
        yield get_status_dict(action="addurls",
                              ds=dataset,
                              status="error",
                              message="Must specify url_file argument")
        return

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
        rows, subpaths = me.extract(fd, input_type,
                                    filename_format, url_format,
                                    exclude_autometa, meta,
                                    missing_value)

    all_files = [row["filename"] for row in rows]
    if len(all_files) != len(set(all_files)):
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
                     row["url"], os.path.join(dataset.path, row["filename"]))
            lgr.info("Metadata: %s", row["meta_args"])
        yield get_status_dict(action="addurls",
                              ds=dataset,
                              status="ok",
                              message="dry-run finished")
        return

    if not dataset.repo:
        # Populate a new dataset with the URLs.
        for r in dataset.create(result_xfm=None, return_type='generator'):
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

    pbar_addurl = ui.get_progressbar(total=len(rows), label="Adding files",
                                     unit=" Files")
    pbar_addurl.start()

    files_to_add = []
    meta_to_add = []
    addurl_results = []
    for row_idx, row in enumerate(rows, 1):
        pbar_addurl.update(row_idx)
        fname_abs = os.path.join(dataset.path, row["filename"])
        if row["subpath"]:
            # Adjust the dataset and filename for an `addurl` call
            # from within the subdataset that will actually contain
            # the link.
            ds_current = Dataset(os.path.join(dataset.path, row["subpath"]))
            ds_filename = os.path.relpath(fname_abs, ds_current.path)
        else:
            ds_current = dataset
            ds_filename = row["filename"]

        if os.path.exists(fname_abs) or os.path.islink(fname_abs):
            if ifexists == "skip":
                addurl_results.append(
                    get_status_dict(action="addurls",
                                    ds=ds_current,
                                    type="file",
                                    path=fname_abs,
                                    status="notneeded"))
                continue
            elif ifexists == "overwrite":
                lgr.debug("Removing %s", fname_abs)
                os.unlink(fname_abs)
            else:
                lgr.debug("File %s already exists", fname_abs)

        try:
            ds_current.repo.add_url_to_file(ds_filename, row["url"],
                                            batch=True, options=annex_options)
        except AnnexBatchCommandError:
            addurl_results.append(
                get_status_dict(action="addurls",
                                ds=ds_current,
                                type="file",
                                path=os.path.join(ds_current.path,
                                                  ds_filename),
                                message="failed to add URL",
                                status="error"))

            continue
        # Collect the status dicts to yield later so that we don't
        # interrupt the progress bar.
        addurl_results.append(
            get_status_dict(action="addurls",
                            ds=ds_current,
                            type="file",
                            path=os.path.join(ds_current.path,
                                              ds_filename),
                            status="ok"))

        files_to_add.append(row["filename"])
        meta_to_add.append((ds_current, ds_filename, row["meta_args"]))
    pbar_addurl.finish()

    for result in addurl_results:
        yield result

        msg = message or """\
[DATALAD] add files from URLs

url_file='{}'
url_format='{}'
filename_format='{}'""".format(url_file, url_format, filename_format)

    if files_to_add:
        for r in dataset.add(files_to_add, message=msg):
            yield r

    # TODO: Wrap this repeated "delayed results/progress bar" pattern.
    pbar_meta = ui.get_progressbar(total=len(meta_to_add),
                                   label="Adding metadata", unit=" Files")
    pbar_meta.start()

    meta_results = []
    for meta_idx, (ds, fname, meta) in enumerate(meta_to_add, 1):
        pbar_meta.update(meta_idx)
        lgr.debug("Adding metadata to %s in %s", fname, ds.path)

        meta_args = []
        for arg in meta:
            meta_args.extend(["--set", arg])
        meta_args.append(fname)

        ds.repo._run_annex_command("metadata", annex_options=meta_args)

        meta_results.append(
            get_status_dict(action="addurls-metadata",
                            ds=ds_current,
                            type="file",
                            path=os.path.join(ds.path, fname),
                            message="added metadata",
                            status="ok"))

    for result in meta_results:
        yield result
