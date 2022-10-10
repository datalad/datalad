# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for managing metadata
"""

__docformat__ = 'restructuredtext'

import logging
from datalad.log import log_progress
lgr = logging.getLogger('datalad.metadata.search')

import os
import re
from functools import partial
from os.path import join as opj, exists
from os.path import relpath
from os.path import normpath
import sys
from time import time

from datalad import cfg
from datalad.consts import SEARCH_INDEX_DOTGITDIR
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.dochelpers import single_or_plural
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.utils import eval_results
from datalad.support.constraints import (
    EnsureInt,
    EnsureNone,
)
from datalad.support.exceptions import (
    CapturedException,
    NoDatasetFound,
)
from datalad.support.param import Parameter
from datalad.ui import ui
from datalad.utils import (
    as_unicode,
    ensure_list,
    ensure_unicode,
    get_suggestions_msg,
    shortened_repr,
    unicode_srctypes,
)
from datalad.metadata.metadata import query_aggregated_metadata

# TODO: consider using plain as_unicode, without restricting
# the types?
_any2unicode = partial(as_unicode, cast_types=(int, float, tuple, list, dict))


def _listdict2dictlist(lst, strict=True):
    """Helper to deal with DataLad's unique value reports

    Parameters
    ----------
    lst : list
      List of dicts
    strict : bool
      In strict mode any dictionary items that doesn't have a simple value
      (but another container) is discarded. In non-strict mode, arbitrary
      levels of nesting are preserved, and no unique-ification of values
      is performed. The latter can be used when it is mostly (or merely)
      interesting to get a list of metadata keys.
    """
    # unique values that we got, always a list
    if all(not isinstance(uval, dict) for uval in lst):
        # no nested structures, take as is
        return lst

    type_excluder = (tuple, list)
    if strict:
        type_excluder += (dict,)
    # we need to turn them inside out, instead of a list of
    # dicts, we want a dict where values are lists, because we
    # cannot handle hierarchies in a tabular search index
    # if you came here to find that out, go ahead and use a graph
    # DB/search
    udict = {}
    for uv in lst:
        if not isinstance(uv, dict):
            # we cannot mix and match, discard any scalar values
            # in favor of the structured metadata
            continue
        for k, v in uv.items():
            if isinstance(v, type_excluder):
                # this is where we draw the line, two levels of
                # nesting. whoosh can only handle string values
                # injecting a stringified blob of something doesn't
                # really enable anything useful -> graph search
                continue
            if v == "":
                # no cruft
                continue
            if strict:
                # no duplicate values, only hashable stuff
                uvals = udict.get(k, set())
                uvals.add(v)
            else:
                # whatever it is, we'll take it
                uvals = udict.get(k, [])
                uvals.append(v)
            udict[k] = uvals
    return {
        # set not good for JSON, have plain list
        k: list(v) if len(v) > 1 else list(v)[0]
        for k, v in udict.items()
        # do not accumulate cruft
        if len(v)}


def _meta2autofield_dict(meta, val2str=True, schema=None, consider_ucn=True):
    """Takes care of dtype conversion into unicode, potential key mappings
    and concatenation of sequence-type fields into CSV strings

    - if `consider_ucn` (default) it would copy keys from
      datalad_unique_content_properties into `meta` for that extractor
    - ... TODO ...
    """
    if consider_ucn:
        # loop over all metadata sources and the report of their unique values
        ucnprops = meta.get("datalad_unique_content_properties", {})
        for src, umeta in ucnprops.items():
            srcmeta = meta.get(src, {})
            for uk in umeta:
                if uk in srcmeta:
                    # we have a real entry for this key in the dataset metadata
                    # ignore any generated unique value list in favor of the
                    # tailored data
                    continue
                srcmeta[uk] = _listdict2dictlist(umeta[uk], strict=False) if umeta[uk] is not None else None
            if src not in meta and srcmeta:
                meta[src] = srcmeta  # assign the new one back

    srcmeta = None   # for paranoids to avoid some kind of manipulation of the last

    def _deep_kv(basekey, dct):
        """Return key/value pairs of any depth following a rule for key
        composition

        dct must be a dict
        """
        for k, v in dct.items():
            if (k != '@id' and k.startswith('@')) or k == 'datalad_unique_content_properties':
                # ignore all JSON-LD specials, but @id
                continue
            # TODO `k` might need remapping, if another key was already found
            # with the same definition
            key = u'{}{}'.format(
                basekey,
                # replace now special chars, and avoid spaces
                # `os.sep` needs to go, because whoosh uses the field name for
                # temp files during index staging, and trips over absent "directories"
                # TODO maybe even kill parentheses
                # TODO actually, it might be better to have an explicit whitelist
                k.lstrip('@').replace(os.sep, '_').replace(' ', '_').replace('-', '_').replace('.', '_').replace(':', '-')
            )
            if isinstance(v, list):
                v = _listdict2dictlist(v)

            if isinstance(v, dict):
                # dive
                for i in _deep_kv('{}.'.format(key), v):
                    yield i
            else:
                yield key, v

    def get_indexer(metadata_format_name: str) -> callable:
        from pkg_resources import EntryPoint, iter_entry_points

        all_indexers = tuple(iter_entry_points('datalad.metadata.indexers', metadata_format_name))
        if all_indexers:
            if len(all_indexers) > 1:
                # Check that there is only one indexer of the requested name.
                # In theory there could be multiple indexers, if different
                # distributions provided the same entry point. So if there is
                # more than one indexer, we know that different distributions
                # have provided elements for the same entry point. Since we
                # do not know which other changes the distributions have made,
                # e.g. API changes, we cannot decide here, which entry point
                # should be used. Issue a warning and use the fall-back indexer.
                lgr.warning(
                    "Multiple indexers for metadata format %s provided by the following distributions: "
                    + ", ".join([str(indexer.dist) for indexer in all_indexers]),
                    metadata_format_name)
            else:
                indexer = all_indexers[0]
                if isinstance(indexer, EntryPoint):
                    try:
                        indexer_object = indexer.load()(metadata_format_name)
                        return indexer_object.create_index
                    except Exception as e:
                        lgr.warning(
                            'Failed to load indexer %s (%s): %s',
                            indexer.name,
                            str(indexer.dist),
                            CapturedException(e))
        lgr.debug(
            'Falling back to standard indexer for metadata format: %s',
            metadata_format_name)
        return lambda metadata: _deep_kv('', metadata)

    if val2str:
        def _val2str_helper(value):
            if isinstance(value, (list, tuple)):
                return u' '.join(_any2unicode(i) for i in value)
            return _any2unicode(value)
    else:
        def _val2str_helper(value):
            return value

    meta = meta or {}
    return {
        # Collect all meta-items which have a non-dict value type and where
        # the key is not absent in a given schema.
        **{
            key: _val2str_helper(value)
            for key, value in filter(lambda kv: not isinstance(kv[1], dict), meta.items())
            if schema is None or key in schema
        },

        # Collect all meta-items which have a dict value type and where
        # the key is neither 'datalad_unique_content_properties' nor absent
        # in a given schema.
        # These values are considered to be metadata, the keys are considered to
        # be the name of the extractor, i.e. the metadata_format_name, that created
        # the metadata.
        **{
            metadata_format_name + '.' + sub_key: _val2str_helper(sub_key_value)
            for metadata_format_name, metadata_content in filter(
                lambda kv: isinstance(kv[1], dict) and kv[0] != 'datalad_unique_content_properties',
                meta.items()
            )
            for sub_key, sub_key_value in get_indexer(metadata_format_name)(metadata_content)
            if schema is None or metadata_format_name + '.' + sub_key in schema
        }
    }


def _search_from_virgin_install(dataset, query):
    #
    # this is to be nice to newbies
    #
    exc_info = sys.exc_info()
    if dataset is None:
        if not ui.is_interactive:
            raise NoDatasetFound(
                "No DataLad dataset found. Specify a dataset to be "
                "searched, or run interactively to get assistance "
                "installing a queryable superdataset."
            )
        # none was provided so we could ask user whether he possibly wants
        # to install our beautiful mega-duper-super-dataset?
        # TODO: following logic could possibly benefit other actions.
        DEFAULT_DATASET_PATH = cfg.obtain('datalad.locations.default-dataset')
        if os.path.exists(DEFAULT_DATASET_PATH):
            default_ds = Dataset(DEFAULT_DATASET_PATH)
            if default_ds.is_installed():
                if ui.yesno(
                    title="No DataLad dataset found at current location",
                    text="Would you like to search the DataLad "
                         "superdataset at %r?"
                          % DEFAULT_DATASET_PATH):
                    pass
                else:
                    raise exc_info[1]
            else:
                raise NoDatasetFound(
                    "No DataLad dataset found at current location. "
                    "The DataLad superdataset location %r exists, "
                    "but does not contain an dataset."
                    % DEFAULT_DATASET_PATH)
        elif ui.yesno(
                title="No DataLad dataset found at current location",
                text="Would you like to install the DataLad "
                     "superdataset at %r?"
                     % DEFAULT_DATASET_PATH):
            from datalad.api import install
            default_ds = install(
                DEFAULT_DATASET_PATH,
                source='///',
                result_renderer='disabled')
            ui.message(
                "From now on you can refer to this dataset using the "
                "label '///'"
            )
        else:
            raise exc_info[1]

        lgr.info(
            "Performing search using DataLad superdataset %r",
            default_ds.path
        )
        for res in default_ds.search(query, result_renderer="disabled"):
            yield res
        return
    else:
        raise  # this function is called within exception handling block


class _Search(object):
    def __init__(self, ds, metadata_source=None, **kwargs):
        self.ds = ds
        self.metadata_source = metadata_source
        self.documenttype = self.ds.config.obtain(
            'datalad.search.index-{}-documenttype'.format(self._mode_label),
            default=self._default_documenttype)

    def __call__(self, query, max_nresults=None):
        raise NotImplementedError

    @classmethod
    def _key_matches(cls, k, regexes):
        """Return which regex the key matches
        """
        for regex in regexes:
            if re.search(regex, k):
                return regex

    def show_keys(self, *args, **kwargs):
        raise NotImplementedError(args)

    def get_query(self, query):
        """Prepare query structure specific for a search backend.

        It can also memorize within instance some parameters of the last query
        which could be used to assist output formatting/structuring later on
        """
        raise NotImplementedError

    def get_nohits_msg(self):
        """Given what it knows, provide recommendation in the case of no hits"""
        return "No search hits, wrong query? " \
               "See 'datalad search --show-keys name' for known keys " \
               "and 'datalad search --help' on how to prepare your query."


class _WhooshSearch(_Search):
    def __init__(self, ds, metadata_source=None, force_reindex=False, **kwargs):
        super(_WhooshSearch, self).__init__(ds, metadata_source, **kwargs)

        self.idx_obj = None
        # where does the bunny have the eggs?

        self.index_dir = opj(str(self.ds.repo.dot_git), SEARCH_INDEX_DOTGITDIR)
        self._mk_search_index(force_reindex)

    def show_keys(self, mode, regexes=None):
        """

        Parameters
        ----------
        mode: {"name"}
        regexes: list of regex
          Which keys to bother working on
        """
        if mode != 'name':
            raise NotImplementedError(
                "ATM %s can show only names, so please use show_keys with 'name'"
                % self.__class__.__name__
            )
        for k in self.idx_obj.schema.names():
            if regexes and not self._key_matches(k, regexes):
                continue
            print(u'{}'.format(k))

    def get_query(self, query):
        # parse the query string
        self._mk_parser()
        # for convenience we accept any number of args-words from the
        # shell and put them together to a single string here
        querystr = ' '.join(ensure_list(query))
        # this gives a formal whoosh query
        wquery = self.parser.parse(querystr)
        return wquery

    def _meta2doc(self, meta, val2str=True, schema=None):
        raise NotImplementedError

    def _mk_schema(self, dsinfo):
        raise NotImplementedError

    def _mk_parser(self):
        raise NotImplementedError

    def _mk_search_index(self, force_reindex):
        """Generic entrypoint to index generation

        The actual work that determines the structure and content of the index
        is done by functions that are passed in as arguments

        `meta2doc` - must return dict for index document from result input
        """
        from whoosh import index as widx
        from .metadata import get_ds_aggregate_db_locations
        dbloc, db_base_path = get_ds_aggregate_db_locations(self.ds)
        # what is the latest state of aggregated metadata
        metadata_state = self.ds.repo.get_last_commit_hexsha(relpath(dbloc, start=self.ds.path))
        # use location common to all index types, they would all invalidate
        # simultaneously
        stamp_fname = opj(self.index_dir, 'datalad_metadata_state')
        index_dir = opj(self.index_dir, self._mode_label)

        if (not force_reindex) and \
                exists(index_dir) and \
                exists(stamp_fname) and \
                open(stamp_fname).read() == metadata_state:
            try:
                # TODO check that the index schema is the same
                # as the one we would have used for reindexing
                # TODO support incremental re-indexing, whoosh can do it
                idx = widx.open_dir(index_dir)
                lgr.debug(
                    'Search index contains %i documents',
                    idx.doc_count())
                self.idx_obj = idx
                return
            except widx.LockError as e:
                raise e
            except widx.IndexError as e:
                # Generic index error.
                # we try to regenerate
                lgr.warning(
                    "Cannot open existing index %s (%s), will regenerate",
                    index_dir, CapturedException(e)
                )
            except widx.IndexVersionError as e:  # (msg, version, release=None)
                # Raised when you try to open an index using a format that the
                # current version of Whoosh cannot read. That is, when the index
                # you're trying to open is either not backward or forward
                # compatible with this version of Whoosh.
                # we try to regenerate
                lgr.warning(CapturedException(e))
                pass
            except widx.OutOfDateError as e:
                # Raised when you try to commit changes to an index which is not
                # the latest generation.
                # this should not happen here, but if it does ... KABOOM
                raise
            except widx.EmptyIndexError as e:
                # Raised when you try to work with an index that has no indexed
                # terms.
                # we can just continue with generating an index
                pass
            except ValueError as e:
                if 'unsupported pickle protocol' in str(e):
                    lgr.warning(
                        "Cannot open existing index %s (%s), will regenerate",
                        index_dir, CapturedException(e)
                    )
                else:
                    raise

        lgr.info('{} search index'.format(
            'Rebuilding' if exists(index_dir) else 'Building'))

        if not exists(index_dir):
            os.makedirs(index_dir)

        # this is a pretty cheap call that just pull this info from a file
        dsinfo = self.ds.metadata(
            get_aggregates=True,
            return_type='list',
            result_renderer='disabled')

        self._mk_schema(dsinfo)

        idx_obj = widx.create_in(index_dir, self.schema)
        idx = idx_obj.writer(
            # cache size per process
            limitmb=cfg.obtain('datalad.search.indexercachesize'),
            # disable parallel indexing for now till #1927 is resolved
            ## number of processes for indexing
            #procs=multiprocessing.cpu_count(),
            ## write separate index segments in each process for speed
            ## asks for writer.commit(optimize=True)
            #multisegment=True,
        )

        # load metadata of the base dataset and what it knows about all its subdatasets
        # (recursively)
        old_idx_size = 0
        old_ds_rpath = ''
        idx_size = 0
        log_progress(
            lgr.info,
            'autofieldidxbuild',
            'Start building search index',
            total=len(dsinfo),
            label='Building search index',
            unit=' Datasets',
        )
        for res in query_aggregated_metadata(
                reporton=self.documenttype,
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                # MIH: I cannot see a case when we would not want recursion (within
                # the metadata)
                recursive=True,
                metadata_source=self.metadata_source):
            # this assumes that files are reported after each dataset report,
            # and after a subsequent dataset report no files for the previous
            # dataset will be reported again
            meta = res.get('metadata', {})
            doc = self._meta2doc(meta)
            admin = {
                'type': res['type'],
                'path': relpath(res['path'], start=self.ds.path),
            }
            if 'parentds' in res:
                admin['parentds'] = relpath(res['parentds'], start=self.ds.path)
            if admin['type'] == 'dataset':
                if old_ds_rpath:
                    lgr.debug(
                        'Added %s on dataset %s',
                        single_or_plural(
                            'document',
                            'documents',
                            idx_size - old_idx_size,
                            include_count=True),
                        old_ds_rpath)
                log_progress(lgr.info, 'autofieldidxbuild',
                             'Indexed dataset at %s', old_ds_rpath,
                             update=1, increment=True)
                old_idx_size = idx_size
                old_ds_rpath = admin['path']
                admin['id'] = res.get('dsid', None)

            doc.update({k: ensure_unicode(v) for k, v in admin.items()})
            lgr.debug("Adding document to search index: {}".format(doc))
            # inject into index
            idx.add_document(**doc)
            idx_size += 1

        if old_ds_rpath:
            lgr.debug(
                'Added %s on dataset %s',
                single_or_plural(
                    'document',
                    'documents',
                    idx_size - old_idx_size,
                    include_count=True),
                old_ds_rpath)

        lgr.debug("Committing index")
        idx.commit(optimize=True)
        log_progress(
            lgr.info, 'autofieldidxbuild', 'Done building search index')

        # "timestamp" the search index to allow for automatic invalidation
        with open(stamp_fname, 'w') as f:
            f.write(metadata_state)

        lgr.info('Search index contains %i documents', idx_size)
        self.idx_obj = idx_obj

    def __call__(self, query, max_nresults=None, force_reindex=False, full_record=False):
        if max_nresults is None:
            # mode default
            max_nresults = 20

        with self.idx_obj.searcher() as searcher:
            wquery = self.get_query(query)

            # perform the actual search
            hits = searcher.search(
                wquery,
                terms=True,
                limit=max_nresults if max_nresults > 0 else None)
            # report query stats
            topstr = '{} top {}'.format(
                max_nresults,
                single_or_plural('match', 'matches', max_nresults)
            )
            lgr.info('Query completed in {} sec.{}'.format(
                hits.runtime,
                ' Reporting {}.'.format(
                    ('up to ' + topstr)
                    if max_nresults > 0
                    else 'all matches'
                )
                if not hits.is_empty()
                else ' No matches.'
            ))

            if not hits:
                return

            nhits = 0
            annotated_hits = []
            # annotate hits for full metadata report
            for i, hit in enumerate(hits):
                annotated_hit = dict(
                    path=normpath(opj(self.ds.path, hit['path'])),
                    query_matched={ensure_unicode(k): ensure_unicode(v)
                                   if isinstance(v, unicode_srctypes) else v
                                   for k, v in hit.matched_terms()},
                    parentds=normpath(
                        opj(self.ds.path, hit['parentds'])) if 'parentds' in hit else None,
                    type=hit.get('type', None))
                if not full_record:
                    annotated_hit.update(
                        refds=self.ds.path,
                        action='search',
                        status='ok',
                        logger=lgr,
                    )
                    yield annotated_hit
                else:
                    annotated_hits.append(annotated_hit)
                nhits += 1
            if full_record:
                for res in query_aggregated_metadata(
                        # type is taken from hit record
                        reporton=None,
                        ds=self.ds,
                        aps=annotated_hits,
                        # never recursive, we have direct hits already
                        recursive=False,
                        metadata_source=self.metadata_source):
                    res.update(
                        refds=self.ds.path,
                        action='search',
                        status='ok',
                        logger=lgr,
                    )
                    yield res

            if max_nresults and nhits == max_nresults:
                lgr.info(
                    "Reached the limit of {}, there could be more which "
                    "were not reported.".format(topstr)
                )


class _BlobSearch(_WhooshSearch):
    _mode_label = 'textblob'
    _default_documenttype = 'datasets'

    def _meta2doc(self, meta):
        # coerce the entire flattened metadata dict into a comma-separated string
        # that also includes the keys
        return dict(meta=u', '.join(
            u'{}: {}'.format(k, v)
            for k, v in _meta2autofield_dict(
                meta,
                val2str=True,
                schema=None).items()))

    def _mk_schema(self, dsinfo):
        from whoosh import fields as wf
        from whoosh.analysis import StandardAnalyzer

        # TODO support some customizable mapping to homogenize some metadata fields
        # onto a given set of index keys
        self.schema = wf.Schema(
            id=wf.ID,
            path=wf.ID(stored=True),
            type=wf.ID(stored=True),
            parentds=wf.ID(stored=True),
            meta=wf.TEXT(
                stored=False,
                analyzer=StandardAnalyzer(minsize=2))
        )

    def _mk_parser(self):
        from whoosh import qparser as qparse

        # use whoosh default query parser for now
        parser = qparse.QueryParser(
            "meta",
            schema=self.idx_obj.schema
        )
        parser.add_plugin(qparse.FuzzyTermPlugin())
        parser.remove_plugin_class(qparse.PhrasePlugin)
        parser.add_plugin(qparse.SequencePlugin())
        self.parser = parser


class _AutofieldSearch(_WhooshSearch):
    _mode_label = 'autofield'
    _default_documenttype = 'all'

    def _meta2doc(self, meta):
        return _meta2autofield_dict(meta, val2str=True, schema=self.schema)

    def _mk_schema(self, dsinfo):
        from whoosh import fields as wf
        from whoosh.analysis import SimpleAnalyzer

        # haven for terms that have been found to be undefined
        # (for faster decision-making upon next encounter)
        # this will harvest all discovered term definitions
        definitions = {
            '@id': 'unique identifier of an entity',
            # TODO make proper JSON-LD definition
            'path': 'path name of an entity relative to the searched base dataset',
            # TODO make proper JSON-LD definition
            'parentds': 'path of the datasets that contains an entity',
            # 'type' will not come from a metadata field, hence will not be detected
            'type': 'type of a record',
        }

        schema_fields = {
            n.lstrip('@'): wf.ID(stored=True, unique=n == '@id')
            for n in definitions}

        lgr.debug('Scanning for metadata keys')
        # quick 1st pass over all dataset to gather the needed schema fields
        log_progress(
            lgr.info,
            'idxschemabuild',
            'Start building search schema',
            total=len(dsinfo),
            label='Building search schema',
            unit=' Datasets',
        )
        for res in query_aggregated_metadata(
                # XXX TODO After #2156 datasets may not necessarily carry all
                # keys in the "unique" summary
                reporton='datasets',
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                recursive=True,
                metadata_source=self.metadata_source):
            meta = res.get('metadata', {})
            # no stringification of values for speed, we do not need/use the
            # actual values at this point, only the keys
            idxd = _meta2autofield_dict(meta, val2str=False)

            for k in idxd:
                schema_fields[k] = wf.TEXT(stored=False,
                                           analyzer=SimpleAnalyzer())
            log_progress(lgr.info, 'idxschemabuild',
                         'Scanned dataset at %s', res['path'],
                         update=1, increment=True)
        log_progress(
            lgr.info, 'idxschemabuild', 'Done building search schema')

        self.schema = wf.Schema(**schema_fields)

    def _mk_parser(self):
        from whoosh import qparser as qparse

        parser = qparse.MultifieldParser(
            self.idx_obj.schema.names(),
            self.idx_obj.schema)
        # XXX: plugin is broken in Debian's whoosh 2.7.0-2, but already fixed
        # upstream
        parser.add_plugin(qparse.FuzzyTermPlugin())
        parser.add_plugin(qparse.GtLtPlugin())
        parser.add_plugin(qparse.SingleQuotePlugin())
        # replace field definition to allow for colons to be part of a field's name:
        parser.replace_plugin(qparse.FieldsPlugin(expr=r"(?P<text>[()<>.\w]+|[*]):"))
        self.parser = parser


class _EGrepCSSearch(_Search):
    _mode_label = 'egrepcs'
    _default_documenttype = 'datasets'

    def __init__(self, ds, metadata_source='all', **kwargs):
        super(_EGrepCSSearch, self).__init__(ds, metadata_source, **kwargs)
        self._queried_keys = None  # to be memoized by get_query

    # If there were custom "per-search engine" options, we could expose
    # --consider_ucn - search through unique content properties of the dataset
    #    which might be more computationally demanding
    def __call__(self, query, max_nresults=None, consider_ucn=False, full_record=True):
        if max_nresults is None:
            # no limit by default
            max_nresults = 0
        query = self.get_query(query)

        nhits = 0
        for res in query_aggregated_metadata(
                reporton=self.documenttype,
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                # MIH: I cannot see a case when we would not want recursion (within
                # the metadata)
                recursive=True,
                metadata_source=self.metadata_source):
            # this assumes that files are reported after each dataset report,
            # and after a subsequent dataset report no files for the previous
            # dataset will be reported again
            meta = res.get('metadata', {})
            # produce a flattened metadata dict to search through
            doc = _meta2autofield_dict(meta, val2str=True, consider_ucn=consider_ucn)
            # inject a few basic properties into the dict
            # analog to what the other modes do in their index
            doc.update({
                k: res[k] for k in ('@id', 'type', 'path', 'parentds')
                if k in res})
            # use search instead of match to not just get hits at the start of the string
            # this will be slower, but avoids having to use actual regex syntax at the user
            # side even for simple queries
            # DOTALL is needed to handle multiline description fields and such, and still
            # be able to match content coming for a later field
            lgr.log(7, "Querying %s among %d items", query, len(doc))
            t0 = time()
            matches = {(q['query'] if isinstance(q, dict) else q, k):
                       q['query'].search(v) if isinstance(q, dict) else q.search(v)
                       for k, v in doc.items()
                       for q in query
                       if not isinstance(q, dict) or q['field'].match(k)}
            dt = time() - t0
            lgr.log(7, "Finished querying in %f sec", dt)
            # retain what actually matched
            matched = {k[1]: match.group() for k, match in matches.items() if match}
            # implement AND behavior across query expressions, but OR behavior
            # across queries matching multiple fields for a single query expression
            # for multiple queries, this makes it consistent with a query that
            # has no field specification
            if matched and len(query) == len(set(k[0] for k in matches if matches[k])):
                hit = dict(
                    res,
                    action='search',
                    query_matched=matched,
                )
                yield hit
                nhits += 1
                if max_nresults and nhits == max_nresults:
                    # report query stats
                    topstr = '{} top {}'.format(
                        max_nresults,
                        single_or_plural('match', 'matches', max_nresults)
                    )
                    lgr.info(
                        "Reached the limit of {}, there could be more which "
                        "were not reported.".format(topstr)
                    )
                    break

    def show_keys(self, mode=None, regexes=None):
        """

        Parameters
        ----------
        mode: {"name", "short", "full"}
        regexes: list of regex
          Which keys to bother working on
        """
        maxl = 100  # approx maximal line length for unique values in mode=short
        # use a dict already, later we need to map to a definition
        # meanwhile map to the values

        keys = self._get_keys(mode)

        for k in sorted(keys):
            if regexes and not self._key_matches(k, regexes):
                continue
            if mode == 'name':
                print(k)
                continue

            # do a bit more
            stat = keys[k]
            all_uvals = uvals = sorted(stat.uvals)

            stat.uvals_str = ensure_unicode(
                "{} unique values: ".format(len(all_uvals))
            )

            if mode == 'short':
                # show only up until we fill maxl
                uvals_str = ''
                uvals = []
                for v in all_uvals:
                    appendix = ('; ' if uvals else '') + v
                    if len(uvals_str) + len(appendix) > maxl - len(stat.uvals_str):
                        break
                    uvals.append(v)
                    uvals_str += appendix
            elif mode == 'full':
                pass
            else:
                raise ValueError(
                    "Unknown value for stats. Know full and short")

            stat.uvals_str += '; '.join(uvals)

            if len(all_uvals) > len(uvals):
                stat.uvals_str += \
                    '; +%s' % single_or_plural("value", "values", len(all_uvals) - len(uvals), True)

            print(
                u'{k}\n in  {stat.ndatasets} datasets\n has {stat.uvals_str}'.format(
                k=k, stat=stat
            ))
        # After #2156 datasets may not necessarily carry all
        # keys in the "unique" summary
        lgr.warning('In this search mode, the reported list of metadata keys may be incomplete')


    def _get_keys(self, mode=None):
        """Return keys and their statistics if mode != 'name'."""
        class key_stat:
            def __init__(self):
                self.ndatasets = 0  # how many datasets have this field
                self.uvals = set()

        from collections import defaultdict
        keys = defaultdict(key_stat)
        for res in query_aggregated_metadata(
                # XXX TODO After #2156 datasets may not necessarily carry all
                # keys in the "unique" summary
                reporton='datasets',
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                recursive=True,
                metadata_source=self.metadata_source):
            meta = res.get('metadata', {})
            # inject a few basic properties into the dict
            # analog to what the other modes do in their index
            meta.update({
                k: res.get(k, None) for k in ('@id', 'type', 'path', 'parentds')
                # parentds is tricky all files will have it, but the dataset
                # queried above might not (single dataset), let's force it in
                if k == 'parentds' or k in res})

            # no stringification of values for speed
            idxd = _meta2autofield_dict(meta, val2str=False)

            for k, kvals in idxd.items():
                # TODO deal with conflicting definitions when available
                keys[k].ndatasets += 1
                if mode == 'name':
                    continue
                keys[k].uvals |= self.get_repr_uvalues(kvals)
        return keys

    def get_repr_uvalues(self, kvals):
        kvals_set = set()
        if not kvals:
            return kvals_set
        kvals_iter = (
            kvals
            if hasattr(kvals, '__iter__') and not isinstance(kvals, (str, bytes))
            else [kvals]
        )
        return set(shortened_repr(x, 50) for x in kvals_iter)

    def get_query(self, query):
        query = ensure_list(query)
        simple_fieldspec = re.compile(r"(?P<field>\S*?):(?P<query>.*)")
        quoted_fieldspec = re.compile(r"'(?P<field>[^']+?)':(?P<query>.*)")
        query_rec_matches = [
            simple_fieldspec.match(q) or
            quoted_fieldspec.match(q) or
            q
            for q in query]
        query_group_dicts_only = [
            q.groupdict() for q in query_rec_matches if hasattr(q, 'groupdict')
        ]
        self._queried_keys = [
            qgd['field']
            for qgd in query_group_dicts_only
            if ('field' in qgd and qgd['field'])
        ]
        if len(query_group_dicts_only) != len(query_rec_matches):
            # we had a query element without field specification add
            # None as an indicator of that
            self._queried_keys.append(None)
        # expand matches, compile expressions
        query = [
            {k: self._compile_query(v) for k, v in q.groupdict().items()}
            if hasattr(q, 'groupdict') else self._compile_query(q)
            for q in query_rec_matches
        ]

        # turn "empty" field specs into simple queries
        # this is used to forcibly disable field-based search
        # e.g. when searching for a value
        query = [q['query']
                 if isinstance(q, dict) and q['field'].pattern == '' else q
                 for q in query]
        return query

    def _xfm_query(self, q):
        # implement potential transformations of regex before they get compiled
        return q

    def _compile_query(self, q):
        """xfm and compile the query, with informative exception if query is incorrect
        """
        q_xfmed = self._xfm_query(q)
        try:
            return re.compile(q_xfmed)
        except re.error as exc:
            omsg = " (original: '%s')" % q if q != q_xfmed else ''
            raise ValueError(
                "regular expression '%s'%s is incorrect: %s"
                % (q_xfmed, omsg, exc)
            )

    def get_nohits_msg(self):
        """Given the query and performed search, provide recommendation

        Quite often a key in the query is mistyped or I simply query for something
        which is not actually known.  It requires --show-keys  run first, doing
        visual search etc to mitigate.  Here we can analyze either all queried
        keys are actually known, and if not known -- what would be the ones available.

        Returns
        -------
        str
          A sentence or a paragraph to be logged/output
        """
        #
        queried_keys = self._queried_keys[:]
        if queried_keys and None in queried_keys:
            queried_keys.pop(queried_keys.index(None))
        if not queried_keys:
            return  # No keys were queried, we are of no use here
        known_keys = self._get_keys(mode='name')
        unknown_keys = sorted(list(set(queried_keys).difference(known_keys)))
        if not unknown_keys:
            return  # again we are of no help here
        msg = super(_EGrepCSSearch, self).get_nohits_msg()
        msg += " Following keys were not found in available metadata: %s. " \
              % ", ".join(unknown_keys)
        suggestions_msg = get_suggestions_msg(unknown_keys, known_keys)
        if suggestions_msg:
            msg += ' ' + suggestions_msg
        return msg


class _EGrepSearch(_EGrepCSSearch):
    _mode_label = 'egrep'
    _default_documenttype = 'datasets'

    def _xfm_query(self, q):
        if q == q.lower():
            # we have no upper case symbol in the query, go case-insensitive
            return '(?i){}'.format(q)
        else:
            return q


@build_doc
class Search(Interface):
    """Search dataset metadata

    DataLad can search metadata extracted from a dataset and/or aggregated into
    a superdataset (see the `aggregate-metadata` command). This makes it
    possible to discover datasets, or individual files in a dataset even when
    they are not available locally.

    Ultimately DataLad metadata are a graph of linked data structures. However,
    this command does not (yet) support queries that can exploit all
    information stored in the metadata. At the moment the following search
    modes are implemented that represent different trade-offs between the
    expressiveness of a query and the computational and storage resources
    required to execute a query.

    - egrep (default)

    - egrepcs [case-sensitive egrep]

    - textblob

    - autofield

    An alternative default mode can be configured by tuning the
    configuration variable 'datalad.search.default-mode'::

      [datalad "search"]
        default-mode = egrepcs

    Each search mode has its own default configuration for what kind of
    documents to query. The respective default can be changed via configuration
    variables::

      [datalad "search"]
        index-<mode_name>-documenttype = (all|datasets|files)


    *Mode: egrep/egrepcs*

    These search modes are largely ignorant of the metadata structure, and
    simply perform matching of a search pattern against a flat
    string-representation of metadata. This is advantageous when the query is
    simple and the metadata structure is irrelevant, or precisely known.
    Moreover, it does not require a search index, hence results can be reported
    without an initial latency for building a search index when the underlying
    metadata has changed (e.g. due to a dataset update). By default, these
    search modes only consider datasets and do not investigate records for
    individual files for speed reasons. Search results are reported in the
    order in which they were discovered.

    Queries can make use of Python regular expression syntax
    (https://docs.python.org/3/library/re.html). In `egrep` mode, matching is
    case-insensitive when the query does not contain upper case characters, but
    is case-sensitive when it does. In `egrepcs` mode, matching is always
    case-sensitive. Expressions will match anywhere in a metadata string, not
    only at the start.

    When multiple queries are given, all queries have to match for a search hit
    (AND behavior).

    It is possible to search individual metadata key/value items by prefixing
    the query with a metadata key name, separated by a colon (':'). The key
    name can also be a regular expression to match multiple keys. A query match
    happens when any value of an item with a matching key name matches the query
    (OR behavior). See examples for more information.

    Examples:

      Query for (what happens to be) an author::

        % datalad search haxby

      Queries are case-INsensitive when the query contains no upper case characters,
      and can be regular expressions. Use `egrepcs` mode when it is desired
      to perform a case-sensitive lowercase match::

        % datalad search --mode egrepcs halchenko.*haxby

      This search mode performs NO analysis of the metadata content.  Therefore
      queries can easily fail to match. For example, the above query implicitly
      assumes that authors are listed in alphabetical order.  If that is the
      case (which may or may not be true), the following query would yield NO
      hits::

        % datalad search Haxby.*Halchenko

      The ``textblob`` search mode represents an alternative that is more
      robust in such cases.

      For more complex queries multiple query expressions can be provided that
      all have to match to be considered a hit (AND behavior). This query
      discovers all files (non-default behavior) that match 'bids.type=T1w'
      AND 'nifti1.qform_code=scanner'::

        % datalad -c datalad.search.index-egrep-documenttype=all search bids.type:T1w nifti1.qform_code:scanner

      Key name selectors can also be expressions, which can be used to select
      multiple keys or construct "fuzzy" queries. In such cases a query matches
      when any item with a matching key matches the query (OR behavior).
      However, multiple queries are always evaluated using an AND conjunction.
      The following query extends the example above to match any files that
      have either 'nifti1.qform_code=scanner' or 'nifti1.sform_code=scanner'::

        % datalad -c datalad.search.index-egrep-documenttype=all search bids.type:T1w nifti1.(q|s)form_code:scanner

    *Mode: textblob*

    This search mode is very similar to the ``egrep`` mode, but with a few key
    differences. A search index is built from the string-representation of
    metadata records. By default, only datasets are included in this index, hence
    the indexing is usually completed within a few seconds, even for hundreds
    of datasets. This mode uses its own query language (not regular expressions)
    that is similar to other search engines. It supports logical conjunctions
    and fuzzy search terms. More information on this is available from the Whoosh
    project (search engine implementation):

      - Description of the Whoosh query language:
        http://whoosh.readthedocs.io/en/latest/querylang.html)

      - Description of a number of query language customizations that are
        enabled in DataLad, such as, fuzzy term matching:
        http://whoosh.readthedocs.io/en/latest/parsing.html#common-customizations

    Importantly, search hits are scored and reported in order of descending
    relevance, hence limiting the number of search results is more meaningful
    than in the 'egrep' mode and can also reduce the query duration.

    Examples:

      Search for (what happens to be) two authors, regardless of the order in
      which those names appear in the metadata::

        % datalad search --mode textblob halchenko haxby

      Fuzzy search when you only have an approximate idea what you are looking
      for or how it is spelled::

        % datalad search --mode textblob haxbi~

      Very fuzzy search, when you are basically only confident about the first
      two characters and how it sounds approximately (or more precisely: allow
      for three edits and require matching of the first two characters)::

        % datalad search --mode textblob haksbi~3/2

      Combine fuzzy search with logical constructs::

        % datalad search --mode textblob 'haxbi~ AND (hanke OR halchenko)'


    *Mode: autofield*

    This mode is similar to the 'textblob' mode, but builds a vastly more
    detailed search index that represents individual metadata variables as
    individual fields. By default, this search index includes records for
    datasets and individual fields, hence it can grow very quickly into
    a huge structure that can easily take an hour or more to build and require
    more than a GB of storage. However, limiting it to documents on datasets
    (see above) retains the enhanced expressiveness of queries while
    dramatically reducing the resource demands.

    Examples:

      List names of search index fields (auto-discovered from the set of
      indexed datasets) which either have a field starting with "age" or
      "gender"::

        % datalad search --mode autofield --show-keys name '\\.age' '\\.gender'

      Fuzzy search for datasets with an author that is specified in a particular
      metadata field::

        % datalad search --mode autofield bids.author:haxbi~ type:dataset

      Search for individual files that carry a particular description
      prefix in their 'nifti1' metadata::

        % datalad search --mode autofield nifti1.description:FSL* type:file


    *Reporting*

    Search hits are returned as standard DataLad results. On the command line
    the '--output-format' (or '-f') option can be used to tweak results for
    further processing.

    Examples:

      Format search hits as a JSON stream (one hit per line)::

        % datalad -f json search haxby

      Custom formatting: which terms matched the query of particular
      results. Useful for investigating fuzzy search results::

        $ datalad -f '{path}: {query_matched}' search --mode autofield bids.author:haxbi~
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the query operation on. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        query=Parameter(
            args=("query",),
            metavar='QUERY',
            nargs="*",
            doc="""query string, supported syntax and features depends on the
            selected search mode (see documentation)"""),
        force_reindex=Parameter(
            args=("--reindex",),
            dest='force_reindex',
            action='store_true',
            doc="""force rebuilding the search index, even if no change in the
            dataset's state has been detected, for example, when the index
            documenttype configuration has changed."""),
        max_nresults=Parameter(
            args=("--max-nresults",),
            doc="""maximum number of search results to report. Setting this
            to 0 will report all search matches. Depending on the mode this
            can search substantially slower. If not specified, a
            mode-specific default setting will be used.""",
            constraints=EnsureInt() | EnsureNone()),
        mode=Parameter(
            args=("--mode",),
            choices=('egrep', 'textblob', 'autofield'),
            doc="""Mode of search index structure and content. See section
            SEARCH MODES for details."""),
        full_record=Parameter(
            args=("--full-record", '-f'),
            action='store_true',
            doc="""If set, return the full metadata record for each search hit.
            Depending on the search mode this might require additional queries.
            By default, only data that is available to the respective search modes
            is returned. This always includes essential information, such as the
            path and the type."""),
        show_keys=Parameter(
            args=('--show-keys',),
            choices=('name', 'short', 'full'),
            default=None,
            doc="""if given, a list of known search keys is shown. If 'name' -
            only the name is printed one per line. If 'short' or 'full',
            statistics (in how many datasets, and how many unique values) are
            printed. 'short' truncates the listing of unique values.
            QUERY, if provided, is regular expressions any of which keys should
            contain.
            No other action is performed (except for reindexing), even if other
            arguments are given. Each key is accompanied by a term definition in
            parenthesis (TODO). In most cases a definition is given in the form
            of a URL. If an ontology definition for a term is known, this URL
            can resolve to a webpage that provides a comprehensive definition
            of the term. However, for speed reasons term resolution is solely done
            on information contained in a local dataset's metadata, and definition
            URLs might be outdated or point to no longer existing resources."""),
        show_query=Parameter(
            args=('--show-query',),
            action='store_true',
            doc="""if given, the formal query that was generated from the given
            query string is shown, but not actually executed. This is mostly useful
            for debugging purposes."""),
        metadata_source=Parameter(
            args=('--metadata-source',),
            choices=('legacy', 'gen4', 'all'),
            doc="""if given, defines which metadata source will be used to
            search. 'legacy' will limit search to metadata in the old format,
            i.e. stored in '$DATASET/.datalad/metadata'. 'gen4' will limit
            search to metadata stored by the git-backend of 
            'datalad-metadata-model'. If 'all' is given, metadata from all
            supported sources will be included in the search. The default is
            'legacy'.""")
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query=None,
                 *,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=None,
                 mode=None,
                 full_record=False,
                 show_keys=None,
                 show_query=False,
                 metadata_source='legacy'):
        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
            if ds.id is None:
                raise NoDatasetFound(
                    "This does not seem to be a dataset (no DataLad dataset ID "
                    "found). 'datalad create --force %s' can initialize "
                    "this repository as a DataLad dataset" % ds.path)
        except NoDatasetFound:
            for r in _search_from_virgin_install(dataset, query):
                yield r
            return

        if mode is None:
            # let's get inspired by what the dataset/user think is
            # default
            mode = ds.config.obtain('datalad.search.default-mode')

        if mode == 'egrep':
            searcher = _EGrepSearch
        elif mode == 'egrepcs':
            searcher = _EGrepCSSearch
        elif mode == 'textblob':
            searcher = _BlobSearch
        elif mode == 'autofield':
            searcher = _AutofieldSearch
        else:
            raise ValueError(
                'unknown search mode "{}"'.format(mode))

        searcher = searcher(
            ds,
            metadata_source=metadata_source,
            force_reindex=force_reindex
        )

        if show_keys:
            searcher.show_keys(show_keys, regexes=query)
            return

        if not query:
            return

        if show_query:
            print(repr(searcher.get_query(query)))
            return

        nhits = 0
        for r in searcher(
                query,
                max_nresults=max_nresults,
                full_record=full_record):
            nhits += 1
            yield r
        if not nhits:
            lgr.info(searcher.get_nohits_msg() or 'no hits')
