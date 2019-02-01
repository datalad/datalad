# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run one or more metadata extractors on a dataset or file(s)"""

__docformat__ = 'restructuredtext'

from os import curdir
import os.path as op
import re
import logging
from six import (
    binary_type,
    string_types,
    iteritems,
)
from collections import (
    Mapping,
)

from datalad import cfg
from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
    EnsureChoice,
    EnsureBool,
)
from datalad.metadata.metadata import (
    _get_metadatarelevant_paths,
    get_metadata_type,
)
from datalad.metadata.definitions import version as vocabulary_version
from datalad.utils import (
    assure_list,
    as_unicode,
)
from datalad.dochelpers import exc_str
from datalad.log import log_progress

# API commands needed
from datalad.distribution.subdatasets import Subdatasets

lgr = logging.getLogger('datalad.metadata.metadata')


@build_doc
class ExtractMetadata(Interface):
    """Run one or more of DataLad's metadata extractors on a dataset or file.

    The result(s) are structured like the metadata DataLad would extract
    during metadata aggregation. There is one result per dataset/file.

    Examples:

      Extract metadata with two extractors from a dataset in the current directory
      and also from all its files::

        $ datalad extract-metadata -d . --source frictionless_datapackage --source datalad_core

      Extract XMP metadata from a single PDF that is not part of any dataset::

        $ datalad extract-metadata --source xmp Downloads/freshfromtheweb.pdf
    """

    _params_ = dict(
        sources=Parameter(
            args=("--source",),
            dest="sources",
            metavar=("NAME"),
            action='append',
            doc="""Name of a metadata extractor to be executed.
            If none is given, a set of default configured extractors,
            plus any extractors enabled in a dataset's configuration
            and invoked.
            [CMD: This option can be given more than once CMD]"""),
        reporton=Parameter(
            args=("--reporton",),
            doc="""dataset component type to report metadata on. If 'all',
            metadata will be reported for the entire dataset and its content.
            If not specified, the dataset's configuration will determine
            the selection, and will default to 'all'.""",
            constraints=EnsureChoice(None, 'all', 'dataset', 'content')),
        path=Parameter(
            args=("path",),
            metavar="FILE",
            nargs="*",
            doc="Path of a file to extract metadata from.",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""Dataset to extract metadata from. If no path is given,
            metadata is extracted from all files of the dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='extract_metadata')
    @eval_results
    def __call__(dataset=None, path=None, sources=None, reporton=None):
        ds = dataset = require_dataset(
            dataset or curdir,
            purpose="extract metadata",
            check_installed=not path)

        if not sources:
            sources = ['datalad_core', 'annex'] \
                + assure_list(get_metadata_type(dataset))

        if not path:
            ds = require_dataset(dataset, check_installed=True)
            subds = ds.subdatasets(recursive=False, result_xfm='relpaths')
            # TODO make it possible to pass a path-generator to help
            # with looong lists
            paths = list(_get_metadatarelevant_paths(ds, subds))
        else:
            paths = assure_list(path)

        res_props = dict(
            action='metadata',
            refds=dataset.path,
        )

        dsmeta = dict()
        contentmeta = {}

        fullpathlist = paths
        if paths and isinstance(ds.repo, AnnexRepo):
            # Ugly? Jep: #2055
            content_info = zip(paths, ds.repo.file_has_content(paths), ds.repo.is_under_annex(paths))
            paths = [p for p, c, a in content_info if not a or c]
            nocontent = len(fullpathlist) - len(paths)
            if nocontent:
                # TODO better fail, or support incremental and label this file as no present
                lgr.warn(
                    '{} files have no content present, '
                    'some extractors will not operate on {}'.format(
                        nocontent,
                        'them' if nocontent > 10
                               else [p for p, c, a in content_info if not c and a])
                )

        # pull out potential metadata field blacklist config settings
        blacklist = [re.compile(bl) for bl in assure_list(ds.config.obtain(
            'datalad.metadata.aggregate-ignore-fields',
            default=[]))]
        # enforce size limits
        max_fieldsize = ds.config.obtain('datalad.metadata.maxfieldsize')
        # keep local, who knows what some extractors might pull in
        from pkg_resources import iter_entry_points  # delayed heavy import
        extractors = {ep.name: ep for ep in iter_entry_points('datalad.metadata.extractors')}

        log_progress(
            lgr.info,
            'metadataextractors',
            'Start metadata extraction from %s', ds,
            total=len(sources),
            label='Metadata extraction',
            unit=' extractors',
        )
        for msrc in sources:
            msrc_key = msrc
            log_progress(
                lgr.info,
                'metadataextractors',
                'Engage %s metadata extractor', msrc_key,
                update=1,
                increment=True)
            want_dataset_meta = reporton in ('all', 'dataset') if reporton else \
                ds.config.obtain(
                    'datalad.metadata.aggregate-dataset-{}'.format(
                        msrc.replace('_', '-')),
                    default=True,
                    valtype=EnsureBool())
            want_content_meta = reporton in ('all', 'content') if reporton else \
                ds.config.obtain(
                    'datalad.metadata.aggregate-content-{}'.format(
                        msrc.replace('_', '-')),
                    default=True,
                    valtype=EnsureBool())
            want_unique = ds.config.obtain(
                'datalad.metadata.generate-unique-{}'.format(
                    msrc_key.replace('_', '-')),
                default=True,
                valtype=EnsureBool())

            if not (want_dataset_meta or want_content_meta):
                log_progress(
                    lgr.info,
                    'metadataextractors',
                    'Skipping %s metadata extraction from %s, disabled by configuration',
                    msrc_key, ds,
                )
                continue
            if msrc_key not in extractors:
                # we said that we want to fail, rather then just moan about less metadata
                log_progress(
                    lgr.error,
                    'metadataextractors',
                    'Failed %s metadata extraction from %s', msrc_key, ds,
                )
                raise ValueError(
                    'Enabled metadata extractor %s is not available in this installation',
                    msrc_key)
            try:
                extractor_cls = extractors[msrc_key].load()
                extractor = extractor_cls(
                    ds,
                    paths=paths if extractor_cls.NEEDS_CONTENT else fullpathlist)
            except Exception as e:
                log_progress(
                    lgr.error,
                    'metadataextractors',
                    'Failed %s metadata extraction from %s', msrc_key, ds,
                )
                raise ValueError(
                    "Failed to load metadata extractor for '%s', "
                    "broken dataset configuration (%s)?: %s",
                    msrc, ds, exc_str(e))
                continue
            try:
                dsmeta_t, contentmeta_t = extractor.get_metadata(
                    dataset=want_dataset_meta,
                    content=want_content_meta,
                )
            except Exception as e:
                if cfg.get('datalad.runtime.raiseonerror'):
                    log_progress(
                        lgr.error,
                        'metadataextractors',
                        'Failed %s metadata extraction from %s', msrc_key, ds,
                    )
                    raise
                yield get_status_dict(
                    ds=dataset,
                    # any errors will have been reported before
                    status='error',
                    message=('Failed to get %s metadata (%s): %s',
                             dataset, msrc, exc_str(e)),
                    **res_props
                )
                continue

            if dsmeta_t:
                if _ok_metadata(dsmeta_t, msrc, ds, None):
                    dsmeta_t = _filter_metadata_fields(
                        dsmeta_t,
                        maxsize=max_fieldsize,
                        blacklist=blacklist)
                    dsmeta[msrc_key] = dsmeta_t
                else:
                    # TODO make _ok_metadata report the actual error and relay it
                    yield get_status_dict(
                        ds=dataset,
                        status='error',
                        message=('Invalid dataset metadata (%s): %s',
                                 msrc, dataset),
                        **res_props
                    )

            unique_cm = {}
            extractor_unique_exclude = getattr(extractor_cls, "_unique_exclude", set())
            # TODO: ATM neuroimaging extractors all provide their own internal
            #  log_progress but if they are all generators, we could provide generic
            #  handling of the progress here.  Note also that log message is actually
            #  seems to be ignored and not used, only the label ;-)
            # log_progress(
            #     lgr.debug,
            #     'metadataextractors_loc',
            #     'Metadata extraction per location for %s', msrc,
            #     # contentmeta_t is a generator... so no cound is known
            #     # total=len(contentmeta_t or []),
            #     label='Metadata extraction per location',
            #     unit=' locations',
            # )
            for loc, meta in contentmeta_t or {}:
                absloc = op.join(dataset.path, loc)
                lgr.log(5, "Analyzing metadata for %s", absloc)
                # log_progress(
                #     lgr.debug,
                #     'metadataextractors_loc',
                #     'ignoredatm',
                #     label=loc,
                #     update=1,
                #     increment=True)
                if not _ok_metadata(meta, msrc, ds, loc):
                    yield get_status_dict(
                        path=absloc,
                        type='file',
                        # any errors will have been reported before
                        status='error',
                        message=('Invalid content metadata (%s): %s',
                                 msrc, absloc),
                        **res_props
                    )
                    # log_progress(
                    #     lgr.debug,
                    #     'metadataextractors_loc',
                    #     'ignoredatm',
                    #     label='Failed for %s' % loc,
                    # )
                    continue
                # we also want to store info that there was no metadata(e.g. to get a list of
                # files that have no metadata)
                # if there is an issue that a extractor needlessly produces empty records, the
                # extractor should be fixed and not a general switch. For example the datalad_core
                # issues empty records to document the presence of a file
                #elif not meta:
                #    continue

                # apply filters
                meta = _filter_metadata_fields(
                    meta,
                    maxsize=max_fieldsize,
                    blacklist=blacklist)

                if not meta:
                    continue

                # assign
                # only ask each metadata extractor once, hence no conflict possible
                loc_dict = contentmeta.get(loc, {})
                loc_dict[msrc_key] = meta
                contentmeta[loc] = loc_dict

                # TODO yield content meta here

                if want_unique:
                    # go through content metadata and inject report of unique keys
                    # and values into `dsmeta`
                    for k, v in iteritems(meta):
                        if k in dsmeta.get(msrc_key, {}):
                            # if the dataset already has a dedicated idea
                            # about a key, we skip it from the unique list
                            # the point of the list is to make missing info about
                            # content known in the dataset, not to blindly
                            # duplicate metadata. Example: list of samples data
                            # were recorded from. If the dataset has such under
                            # a 'sample' key, we should prefer that, over an
                            # aggregated list of a hopefully-kinda-ok structure
                            continue
                        elif k in extractor_unique_exclude:
                            # the extractor thinks this key is worthless for the purpose
                            # of discovering whole datasets
                            # we keep the key (so we know that some file is providing this key),
                            # but ignore any value it came with
                            unique_cm[k] = None
                            continue
                        vset = unique_cm.get(k, set())
                        vset.add(_val2hashable(v))
                        unique_cm[k] = vset

            # log_progress(
            #     lgr.debug,
            #     'metadataextractors_loc',
            #     'Finished metadata extraction across locations for %s', msrc)

            if unique_cm:
                # per source storage here too
                ucp = dsmeta.get('datalad_unique_content_properties', {})
                # important: we want to have a stable order regarding
                # the unique values (a list). we cannot guarantee the
                # same order of discovery, hence even when not using a
                # set above we would still need sorting. the callenge
                # is that any value can be an arbitrarily complex nested
                # beast
                # we also want to have each unique value set always come
                # in a top-level list, so we known if some unique value
                # was a list, os opposed to a list of unique values

                def _ensure_serializable(val):
                    if isinstance(val, ReadOnlyDict):
                        return {k: _ensure_serializable(v) for k, v in iteritems(val)}
                    if isinstance(val, (tuple, list)):
                        return [_ensure_serializable(v) for v in val]
                    else:
                        return val

                ucp[msrc_key] = {
                    k: [_ensure_serializable(i)
                        for i in sorted(
                            v,
                            key=_unique_value_key)] if v is not None else None
                    for k, v in iteritems(unique_cm)
                    # v == None (disable unique, but there was a value at some point)
                    # otherwise we only want actual values, and also no single-item-lists
                    # of a non-value
                    # those contribute no information, but bloat the operation
                    # (inflated number of keys, inflated storage, inflated search index, ...)
                    if v is None or (v and not v == {''})}
                dsmeta['datalad_unique_content_properties'] = ucp

        log_progress(
            lgr.info,
            'metadataextractors',
            'Finished metadata extraction from %s', ds,
        )

        # always identify the effective vocabulary - JSON-LD style
        dsmeta['@context'] = {
            '@vocab': 'http://docs.datalad.org/schema_v{}.json'.format(
                vocabulary_version)}

        if dataset is not None and dataset.is_installed():
            yield get_status_dict(
                ds=dataset,
                metadata=dsmeta,
                # any errors will have been reported before
                status='ok',
                **res_props
            )

        for p in contentmeta:
            res = get_status_dict(
                path=op.join(dataset.path, p) if dataset else p,
                metadata=contentmeta[p],
                type='file',
                # any errors will have been reported before
                status='ok',
                **res_props
            )
            if dataset:
                res['parentds'] = dataset.path
            yield res


def _val2hashable(val):
    """Small helper to convert incoming mutables to something hashable

    The goal is to be able to put the return value into a set, while
    avoiding conversions that would result in a change of representation
    in a subsequent JSON string.
    """
    if isinstance(val, dict):
        return ReadOnlyDict(val)
    elif isinstance(val, list):
        return tuple(map(_val2hashable, val))
    else:
        return val


def _unique_value_key(x):
    """Small helper for sorting unique content metadata values"""
    if isinstance(x, ReadOnlyDict):
        # turn into an item tuple with keys sorted and values plain
        # or as a hash if *dicts
        x = [(k,
              hash(x[k])
              if isinstance(x[k], ReadOnlyDict) else x[k])
             for k in sorted(x)]
    # we need to force str, because sorted in PY3 refuses to compare
    # any heterogeneous type combinations, such as str/int, tuple(int)/tuple(str)
    return as_unicode(x)


def _filter_metadata_fields(d, maxsize=None, blacklist=None):
    lgr.log(5, "Analyzing metadata fields for maxsize=%s with blacklist=%s on "
            "input with %d entries",
            maxsize, blacklist, len(d))
    orig_keys = set(d.keys())
    if blacklist:
        d = {k: v for k, v in iteritems(d)
             if k.startswith('@') or not any(bl.match(k) for bl in blacklist)}
    if maxsize:
        d = {k: v for k, v in iteritems(d)
             if k.startswith('@') or (len(str(v)
                                      if not isinstance(v, string_types + (binary_type,))
                                      else v) <= maxsize)}
    if len(d) != len(orig_keys):
        lgr.info(
            'Removed metadata field(s) due to blacklisting and max size settings: %s',
            orig_keys.difference(d.keys()))
    return d


def _ok_metadata(meta, msrc, ds, loc):
    if meta is None or isinstance(meta, dict):
        return True

    msg = (
        "Metadata extractor '%s' yielded something other than a dictionary "
        "for dataset %s%s -- this is likely a bug, please consider "
        "reporting it. "
        "This type of native metadata will be ignored. Got: %s",
        msrc,
        ds,
        '' if loc is None else ' content {}'.format(loc),
        repr(meta))
    if cfg.get('datalad.runtime.raiseonerror'):
        raise RuntimeError(*msg)

    lgr.error(*msg)
    return False


class ReadOnlyDict(Mapping):
    # Taken from https://github.com/slezica/python-frozendict
    # License: MIT
    """
    An immutable wrapper around dictionaries that implements the complete
    :py:class:`collections.Mapping` interface. It can be used as a drop-in
    replacement for dictionaries where immutability is desired.
    """
    dict_cls = dict

    def __init__(self, *args, **kwargs):
        self._dict = self.dict_cls(*args, **kwargs)
        self._hash = None

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def copy(self, **add_or_replace):
        return self.__class__(self, **add_or_replace)

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self._dict)

    def __hash__(self):
        if self._hash is None:
            h = 0
            for key, value in iteritems(self._dict):
                h ^= hash((key, _val2hashable(value)))
            self._hash = h
        return self._hash
