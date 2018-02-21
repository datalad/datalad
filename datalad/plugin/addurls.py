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

from collections import Mapping, namedtuple
from functools import partial
import logging
import os
import string

lgr = logging.getLogger("datalad.plugin.addurls")

__docformat__ = "restructuredtext"

RowInfo = namedtuple("RowInfo", ["filename", "url", "meta_args", "subpath"])


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
    """

    def __init__(self, idx_to_name, *args, **kwargs):
        self.idx_to_name = idx_to_name or {}
        super(Formatter, self).__init__(*args, **kwargs)

    def get_value(self, key, args, kwargs):
        """Look for key's value in `args[0]` mapping first.
        """
        # FIXME: This approach will fail for keys that contain "!" and
        # ":" because they'll be interpreted as formatting flags.
        data = args[0]
        if not isinstance(data, Mapping):
            raise ValueError("First positional argument should be mapping")

        try:
            key_int = int(key)
        except ValueError:
            pass
        else:
            return data[self.idx_to_name[key_int]]

        try:
            return data[key]
        except KeyError:
            return super(Formatter, self).get_value(
                key, args, kwargs)


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
            field = "tag"
            value = parts[0]

        if not value:
            # The `url_file` may have an empty value.
            continue

        yield field + "=" + value


def extract(stream, input_type, filename_format, url_format, meta):
    """Extract and format information from `url_file`.

    Parameters
    ----------
    stream : file object
        Items used to construct the file names and URLs.

    All other parameters match those described in `dlplugin`.

    Returns
    -------
    A tuple where the first item is a list with RowInfo instance for
    each row in `stream` and the second item is a set that contains all
    the subdataset paths.
    """
    if input_type == "csv":
        import csv
        csvrows = csv.reader(stream)
        headers = next(csvrows)
        lgr.debug("Taking %s fields from first line as headers: %s",
                  len(headers), headers)
        colidx_to_name = dict(enumerate(headers))
        rows = (dict(zip(headers, r)) for r in csvrows)
    elif input_type == "json":
        import json
        rows = json.load(stream)
        # For json input, we do not support indexing by position,
        # only names.
        colidx_to_name = {}
    else:
        raise ValueError("input_type must be 'csv', 'json', or 'ext'")

    fmt = Formatter(colidx_to_name)
    format_filename = partial(fmt.format, filename_format)
    format_url = partial(fmt.format, url_format)
    # Unlike `filename_format` and `url_format`, `meta` is a list
    # because meta may be given multiple times on the command line.
    formats_meta = [partial(fmt.format, m) for m in meta]

    infos = []
    subpaths = set()
    for row in rows:
        url = format_url(row)
        filename = format_filename(row)

        meta_args = list(clean_meta_args(fmt(row) for fmt in formats_meta))

        subpath = None
        if "//" in filename:
            spaths = []
            for part in filename.split("//")[:-1]:
                path = os.path.join(*(spaths + [part]))
                spaths.append(path)
                subpaths.add(path)
            filename = filename.replace("//", os.path.sep)
            subpath = spaths[-1]
        infos.append(RowInfo(filename, url, meta_args, subpath))
    return infos, subpaths


def dlplugin(dataset=None, url_file=None, input_type="ext",
             url_format="{0}", filename_format="{1}", meta=None,
             message=None, dry_run=False, fast=False):
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
        Like `url_format`, but this format string specifies the file
        to which the URL's content will be downloaded.  The file name
        may contain directories.  The separator "//" can be used to
        indicate that the left-side directory should be created as a
        new subdataset.
    meta : str, optional
        A format string that specifies metadata.  It should be
        structured as "<field>=<value>".  The same placeholders from
        `url_format` can be used.  As an example, "location={3}" would
        mean that the value for the "location" metadata field should
        be set the value of the fourth column.  A plain value is
        shorthand for "tag=<value>".  This option can be given
        multiple times.
    message : str, optional
        Use this message when committing the URL additions.
    dry_run : bool, optional
        Report which URLs would be downloaded to which files and then
        exit.
    fast : bool, optional
        If True, add the URLs, but don't download their content.
        Underneath, this passes the --fast flag to `git annex addurl`.

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

    from datalad.distribution.dataset import Dataset
    from datalad.interface.results import get_status_dict
    import datalad.plugin.addurls as me
    from datalad.support.annexrepo import AnnexRepo
    from datalad.utils import assure_list

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

    if input_type == "ext":
        extension = os.path.splitext(url_file)[1]
        input_type = "json" if extension == ".json" else "csv"

    with open(url_file) as fd:
        rows, subpaths = me.extract(fd, input_type,
                                    filename_format, url_format, meta)

    if dry_run:
        for subpath in subpaths:
            lgr.info("Would create a subdataset at %s", subpath)
        for row in rows:
            lgr.info("Would download %s to %s",
                     row.url, os.path.join(dataset.path, row.filename))
            lgr.info("Metadata: %s", row.meta_args)
        yield get_status_dict(action="addurls",
                              ds=dataset,
                              status="ok",
                              message="dry-run finished")
        return

    if not dataset.repo:
        # Populate a new dataset with the URLs.
        dataset.create()
    elif not isinstance(dataset.repo, AnnexRepo):
        yield get_status_dict(action="addurls",
                              ds=dataset,
                              status="error",
                              message="not an annex repo")
        return

    annex_options = ["--fast"] if fast else []

    for spath in subpaths:
        if os.path.exists(os.path.join(dataset.path, spath)):
            lgr.warning(
                "Not creating subdataset at existing path: %s",
                spath)
        else:
            dataset.create(spath)

    files_to_add = []
    meta_to_add = []
    for row in rows:
        if row.subpath:
            # Adjust the dataset and filename for an `addurl` call
            # from within the subdataset that will actually contain
            # the link.
            ds_current = Dataset(os.path.join(dataset.path, row.subpath))
            ds_filename = os.path.relpath(
                os.path.join(dataset.path, row.filename),
                ds_current.path)
        else:
            ds_current = dataset
            ds_filename = row.filename

        ds_current.repo.add_url_to_file(ds_filename, row.url,
                                        batch=True, options=annex_options)
        yield get_status_dict(action="addurls",
                              ds=ds_current,
                              type="file",
                              path=os.path.join(ds_current.path,
                                                ds_filename),
                              status="ok")

        files_to_add.append(row.filename)
        meta_to_add.append((ds_current, ds_filename, row.meta_args))

        msg = message or """\
[DATALAD] add files from URLs

url_file='{}'
url_format='{}'
filename_format='{}'""".format(url_file, url_format, filename_format)
    for r in dataset.add(files_to_add, message=msg):
        yield r

    for ds, fname, meta in meta_to_add:
        lgr.debug("Adding metadata to %s in %s", fname, ds.path)
        for arg in meta:
            ds.repo._run_annex_command("metadata",
                                       annex_options=["--set", arg, fname])
        yield get_status_dict(action="addurls-metadata",
                              ds=ds_current,
                              type="file",
                              path=os.path.join(ds.path, fname),
                              message="added metadata",
                              status="ok")
