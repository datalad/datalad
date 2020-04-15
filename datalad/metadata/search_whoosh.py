# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
import os
from os.path import join as opj, relpath, exists, normpath

from datalad import cfg
from datalad.consts import SEARCH_INDEX_DOTGITDIR
from datalad.dochelpers import exc_str, single_or_plural
from datalad.log import log_progress
from datalad.metadata.metadata import query_aggregated_metadata
from datalad.metadata.search import lgr
from datalad.metadata.search_base import _Search, _meta2autofield_dict
from datalad.utils import assure_list, assure_unicode, unicode_srctypes


class _WhooshSearch(_Search):
    def __init__(self, ds, force_reindex=False, **kwargs):
        super(_WhooshSearch, self).__init__(ds, **kwargs)

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
        querystr = ' '.join(assure_list(query))
        # this gives a formal whoosh query
        wquery = self.parser.parse(querystr)
        return wquery

    def _meta2doc(self, meta, val2str=True, schema=None):
        raise NotImplementedError

    def _mk_schema(self):
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
        # what is the lastest state of aggregated metadata
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
                    index_dir, exc_str(e)
                )
            except widx.IndexVersionError as e:  # (msg, version, release=None)
                # Raised when you try to open an index using a format that the
                # current version of Whoosh cannot read. That is, when the index
                # you're trying to open is either not backward or forward
                # compatible with this version of Whoosh.
                # we try to regenerate
                lgr.warning(exc_str(e))
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
                        index_dir, exc_str(e)
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
                recursive=True):
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

            doc.update({k: assure_unicode(v) for k, v in admin.items()})
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
                    query_matched={assure_unicode(k): assure_unicode(v)
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
                        recursive=False):
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
                recursive=True):
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
        # replace field defintion to allow for colons to be part of a field's name:
        parser.replace_plugin(qparse.FieldsPlugin(expr=r"(?P<text>[()<>.\w]+|[*]):"))
        self.parser = parser