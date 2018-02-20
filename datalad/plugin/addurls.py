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
import string

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


def extract(stream, input_type, filename_format, url_format):
    """Extract and format information from `url_file`.

    Parameters
    ----------
    stream : file object
        Items used to construct the file names and URLs.

    All other parameters match those described in `dlplugin`.

    Returns
    -------
    A generator that, for each item in `url_file`, yields a tuple that
    contains the formatted filename (with any "//" collapsed to a
    single separator), the formatted url, and a list of subdataset
    paths.  The length of the subdataset paths list will be equal to
    the number of "//" occurrences in the `filename_format`.
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

    for row in rows:
        url = format_url(row)
        filename = format_filename(row)

        subpaths = []
        if "//" in filename:
            for part in filename.split("//")[:-1]:
                subpaths.append(os.path.join(*(subpaths + [part])))
            filename = filename.replace("//", os.path.sep)
        yield filename, url, subpaths


def dlplugin(dataset=None, url_file=None, input_type="ext",
             url_format="{0}", filename_format="{1}",
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
    from itertools import dropwhile
    import logging
    import os

    from datalad.distribution.dataset import Dataset
    from datalad.interface.results import get_status_dict
    import datalad.plugin.addurls as me
    from datalad.support.annexrepo import AnnexRepo

    lgr = logging.getLogger("datalad.plugin.addurls")

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
        info = me.extract(fd, input_type, filename_format, url_format)

        if dry_run:
            for fname, url, _ in info:
                lgr.info("Would download %s to %s",
                         url, os.path.join(dataset.path, fname))
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

        seen_subpaths = set()
        to_add = []
        for fname, url, subpaths in info:
            for spath in subpaths:
                if spath not in seen_subpaths:
                    if os.path.exists(os.path.join(dataset.path, spath)):
                        lgr.warning(
                            "Not creating subdataset at existing path: %s",
                            spath)
                    else:
                        dataset.create(spath)
                seen_subpaths.add(spath)

            if subpaths:
                # Adjust the dataset and filename for an `addurl` call
                # from within the subdataset that will actually contain
                # the link.
                datasets = [Dataset(os.path.join(dataset.path, sp))
                            for sp in subpaths]
                ds_current = next(dropwhile(lambda d: not d.repo,
                                            reversed(datasets)))
                ds_filename = os.path.relpath(
                    os.path.join(dataset.path, fname),
                    ds_current.path)
            else:
                ds_current = dataset
                ds_filename = fname

            ds_current.repo.add_url_to_file(ds_filename, url,
                                            batch=True, options=annex_options)
            yield get_status_dict(action="addurls",
                                  ds=ds_current,
                                  type="file",
                                  path=os.path.join(ds_current.path,
                                                    ds_filename),
                                  status="ok")

            to_add.append(fname)

        msg = message or """\
[DATALAD] add files from URLs

url_file='{}'
url_format='{}'
filename_format='{}'""".format(url_file, url_format, filename_format)
        for r in dataset.add(to_add, message=msg):
            yield r
