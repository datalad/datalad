# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
lgr = logging.getLogger('datalad.metadata.search')

import multiprocessing
import re
import os
from os.path import join as opj, exists
from os.path import relpath
from os.path import normpath
import sys
from six import reraise
from six import string_types
from six import PY3
from gzip import open as gzopen

from datalad import cfg
from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from datalad.distribution.utils import get_git_dir
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureInt
from datalad.support.json_py import dump2fileobj as jsondump2file
from simplejson import load as jsonload
from datalad.metadata.definitions import common_defs
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.metadata import _query_aggregated_metadata
from datalad.metadata.metadata import MetadataDict

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import assure_list
from datalad.utils import assure_unicode
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.ui import ui
from datalad.dochelpers import single_or_plural
from datalad.dochelpers import exc_str

if PY3:
    unicode_srctypes = string_types + (bytes,)
    str_contructor = str
else:
    unicode_srctypes = string_types
    str_contructor = unicode

# regex for a cheap test if something looks like a URL
r_url = re.compile(r"^https?://")


def _any2unicode(val):
    return str_contructor(val) if isinstance(val, (int, float)) else assure_unicode(val)


def _add_document(idx, **kwargs):
    idx.add_document(
        **{assure_unicode(k):
           assure_unicode(v) if isinstance(v, unicode_srctypes) else v
           for k, v in kwargs.items()})


def _meta2index_dict(meta, definitions, ds_defs):
    """Takes care of dtype conversion into unicode, potential key mappings
    and concatenation of sequence-type fields into CSV strings
    """
    return {
        # apply any dataset-specific key mapping
        ds_defs.get(k, k):
        # turn lists into CSV strings
        u', '.join(_any2unicode(i) for i in v) if isinstance(v, (list, tuple)) else
        # dicts into SSV strings
        u'; '.join('{}: {}'.format(_any2unicode(i), _any2unicode(v[i])) for i in v) if isinstance(v, dict) else
        # and the rest into unicode
        _any2unicode(v)
        for k, v in (meta or {}).items()
        # ignore anything that is not defined
        if k in definitions
    }


def _resolve_term(term, definitions, common_defs):
    termdef = common_defs.get(term, {}).get('def', None)
    if termdef is not None:
        if r_url.match(termdef):
            # because is_url('schema:name') -> True
            # and complains on DEBUG about irrelevant stuff (parsing diff)
            return termdef
        else:
            term = termdef

    # not in the common vocabulary
    if ':' in term:
        prefix = term.split(':')[0]
        term = term[len(prefix) + 1:]
        prefix_def = definitions.get(prefix, None)
        prefix_def = prefix_def.get('@id', None) \
            if isinstance(prefix_def, dict) else prefix_def
        if prefix_def is None:
            # try the common defs
            prefix_def = common_defs.get(prefix, {}).get('def', None)
            if prefix_def is None:
                # this key also doesn't have a prefix that is defined in
                # the vocabulary, we are lost -> ignore this key as it
                # cannot possibly be resolved
                lgr.debug(
                    "Cannot resolve term prefix '%s', no definition found",
                    prefix)
                return
        if r_url.match(prefix_def):
            # proper URL, just concat to get full definition
            return u'{}{}'.format(prefix_def, term)
        else:
            # make adhoc definitions
            return u'{} (term: {})'.format(prefix_def, term)
    elif term.startswith('comment<') and term.endswith('>'):
        # catch fields like 'comment<someundefinedkey>'
        return common_defs['comment']['def']
    else:
        # we know nothing about this key, ignore
        lgr.debug(
            "Cannot resolve term '%s', no definition found",
            term)
        return


def _get_search_schema(ds):
    from whoosh import fields as wf

    # this will harvest all discovered term definitions
    definitions = {
        '@id': 'unique identifier of an entity',
        # TODO make proper JSON-LD definition
        'path': 'path name of an entity relative to the searched base dataset',
        # TODO make proper JSON-LD definition
        'parentds': 'path of the datasets that contains an entity',
        # 'type' will not come from a metadata field, hence will not be detected
        'type': {
            '@id': _resolve_term(common_defs['type']['def'], {}, common_defs),
            'description': common_defs['type']['descr']},
    }

    schema_fields = {
        n: wf.ID(stored=True, unique=n == '@id')
        for n in definitions}
    # this will contain any dataset-specific term mappings, in case we find
    # non-unique keys that are differently defined
    per_ds_defs = {}
    ds_defs = {}

    lgr.info('Scanning for metadata keys')
    # quick 1st pass over all dataset to gather the needed schema fields
	# sanitization of / should ideally be done while saving, but that would require
	# fixes in whoosh I guess
    sanitize_key = lambda k: k.replace(' ', '_').replace('/', '_')
    for res in _query_aggregated_metadata(
            reporton='datasets',
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            merge_mode='init',
            recursive=True):
        ds_defs = {}
        meta = res.get('metadata', {})
        for k, v in meta.get('@context', {}).items():
            k = sanitize_key(k)
            if k not in definitions or definitions[k] == v:
                # this is new, but unique, or uniformly defined
                definitions[k] = v
            else:
                # non-unique key (across all seen datasets)
                # make unique
                # TODO we have to deal with @vocab fields in here, those
                # might be different when some aggregated metadata was
                # generated with an old version of datalad
                # in this case we should actually load the old vocabulary
                #set.add(', '.join(i for i in v) if isinstance(v, (tuple, list)) else v)
                # and perform the mapping to the current one in here
                count = 0
                uk = k
                while uk in definitions:
                    if definitions[uk] == v:
                        break  # already exists and matches
                    count += 1
                    uk = '{}_{}'.format(k, count)
                ds_defs[k] = k = uk
            definitions[k] = v
            # we register a field for any definition in the context.
            # while this has the potential to needlessly blow up the
            # index size, the only alternative would be to iterate over
            # all content metadata in this first pass too, in order to
            # do a full scan.
            if k == '@vocab' or isinstance(v, dict) and v.get('type', None) == vocabulary_id:
                continue
            schema_fields[k] = wf.TEXT(stored=True)
        if ds_defs:
            # store ds-specific mapping for the second pass that actually
            # generates the search index
            per_ds_defs[res['path']] = ds_defs

        # anything that is a direct metadata key or is reported as being a content metadata
        # key is a valid candidate for inclusion into the schema
        cand_keys = list(meta)
        cand_keys.extend(meta.get('unique_content_properties', []))
        for k in cand_keys:
            k = sanitize_key(k)
            if k in ('unique_content_properties', '@context'):
                # those are just means for something else and irrelevant
                # for searches
                continue
            # check if we have any kind of definitions for this key
            if k not in definitions:
                termdef = _resolve_term(k, definitions, common_defs)
                if termdef is None:
                    # we know nothing about this key, ignore
                    lgr.debug(
                        "Ignoring term '%s', no definition found",
                        k)
                    continue
                definitions[k] = termdef
                # TODO treat keywords/tags separately
                schema_fields[k] = wf.TEXT(stored=True)
            else:
                if isinstance(definitions[k], dict):
                    definitions[k] = {
                        k_ if k_ == '@id' else '{} ({})'.format(
                           k_,
                           _resolve_term(k_, definitions, common_defs))
                        : _resolve_term(v, definitions, common_defs)
                        for k_, v in definitions[k].items()
                        if v  # skip if value is empty
                    }

    schema = wf.Schema(**schema_fields)
    return schema, definitions, per_ds_defs


def _get_search_index(index_dir, ds, force_reindex):
    from whoosh import index as widx
    from .metadata import agginfo_relpath
    # what is the lastest state of aggregated metadata
    metadata_state = ds.repo.get_last_commit_hash(agginfo_relpath)
    stamp_fname = opj(index_dir, 'datalad_metadata_state')
    definitions_fname = opj(index_dir, 'datalad_term_definitions.json.gz')

    if not force_reindex and \
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
            return idx
        except widx.LockError as e:
            raise e
        except widx.IndexError as e:
            # Generic index error.
            # we try to regenerate
            # TODO log this
            pass
        except widx.IndexVersionError as e:  # (msg, version, release=None)
            # Raised when you try to open an index using a format that the
            # current version of Whoosh cannot read. That is, when the index
            # you're trying to open is either not backward or forward
            # compatible with this version of Whoosh.
            # we try to regenerate
            # TODO log this
            pass
        except widx.OutOfDateError as e:
            # Raised when you try to commit changes to an index which is not
            # the latest generation.
            # this should not happen here, but if it does ... KABOOM
            raise e
        except widx.EmptyIndexError as e:
            # Raised when you try to work with an index that has no indexed
            # terms.
            # we can just continue with generating an index
            pass

    lgr.info('{} search index'.format(
        'Rebuilding' if exists(index_dir) else 'Building'))

    if not exists(index_dir):
        os.makedirs(index_dir)

    schema, definitions, per_ds_defs = _get_search_schema(ds)

    idx_obj = widx.create_in(index_dir, schema)
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
    for res in _query_aggregated_metadata(
            reporton=ds.config.obtain('datalad.metadata.searchindex-documenttype'),
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            # TODO expose? but this would likely only affect metadata in the
            # base dataset
            merge_mode='init',
            # MIH: I cannot see a case when we would not want recursion (within
            # the metadata)
            recursive=True):
        rpath = relpath(res['path'], start=ds.path)
        # this assumes that files are reported after each dataset report,
        # and after a subsequent dataset report no files for the previous
        # dataset will be reported again
        rtype = res['type']
        meta = res.get('metadata', {})
        meta = MetadataDict(meta)
        if rtype == 'dataset':
            if old_ds_rpath:
                lgr.info(
                    'Added %s on dataset %s',
                    single_or_plural(
                        'document',
                        'documents',
                        idx_size - old_idx_size,
                        include_count=True),
                    old_ds_rpath)
            old_idx_size = idx_size
            old_ds_rpath = rpath

            # get any custom dataset mappings
            ds_defs = per_ds_defs.get(res['path'], {})
            # now we merge all reported unique content properties (flattened representation
            # of content metadata) with the main metadata set, using the 'add' strategy
            # this way any existing metadata value of a dataset itself will be amended by
            # those coming from the content. E.g. a single dataset 'license' might be turned
            # into a sequence of unique license identifiers across all dataset components
            meta.merge_add(meta.get('unique_content_properties', {}))
            meta.pop('unique_content_properties', None)
        doc_props = dict(
            path=rpath,
            type=rtype,
            **_meta2index_dict(meta, definitions, ds_defs))
        if 'parentds' in res:
            doc_props['parentds'] = relpath(res['parentds'], start=ds.path)
        _add_document(idx, **doc_props)
        idx_size += 1

    if old_ds_rpath:
        lgr.info(
            'Added %s on dataset %s',
            single_or_plural(
                'document',
                'documents',
                idx_size - old_idx_size,
                include_count=True),
            old_ds_rpath)

    idx.commit(optimize=True)

    # "timestamp" the search index to allow for automatic invalidation
    with open(stamp_fname, 'w') as f:
        f.write(metadata_state)

    # dump the term/field definitions records for later introspection
    # use compressed storage, the is not point in inflating the
    # diskspace requirements
    with gzopen(definitions_fname, 'wb') as f:
        # TODO actually go through all, incl. compound, defintions ('@id' plus 'unit'
        # or similar) and resolve terms to URLs, if anyhow possible
        jsondump2file(definitions, f)

    lgr.info('Search index contains %i documents', idx_size)
    return idx_obj


def _search_from_virgin_install(dataset, query):
    #
    # this is to be nice to newbies
    #
    exc_info = sys.exc_info()
    if dataset is None:
        if not ui.is_interactive:
            raise NoDatasetArgumentFound(
                "No DataLad dataset found. Specify a dataset to be "
                "searched, or run interactively to get assistance "
                "installing a queriable superdataset."
            )
        # none was provided so we could ask user either he possibly wants
        # to install our beautiful mega-duper-super-dataset?
        # TODO: following logic could possibly benefit other actions.
        if os.path.exists(LOCAL_CENTRAL_PATH):
            central_ds = Dataset(LOCAL_CENTRAL_PATH)
            if central_ds.is_installed():
                if ui.yesno(
                    title="No DataLad dataset found at current location",
                    text="Would you like to search the DataLad "
                         "superdataset at %r?"
                          % LOCAL_CENTRAL_PATH):
                    pass
                else:
                    reraise(*exc_info)
            else:
                raise NoDatasetArgumentFound(
                    "No DataLad dataset found at current location. "
                    "The DataLad superdataset location %r exists, "
                    "but does not contain an dataset."
                    % LOCAL_CENTRAL_PATH)
        elif ui.yesno(
                title="No DataLad dataset found at current location",
                text="Would you like to install the DataLad "
                     "superdataset at %r?"
                     % LOCAL_CENTRAL_PATH):
            from datalad.api import install
            central_ds = install(LOCAL_CENTRAL_PATH, source='///')
            ui.message(
                "From now on you can refer to this dataset using the "
                "label '///'"
            )
        else:
            reraise(*exc_info)

        lgr.info(
            "Performing search using DataLad superdataset %r",
            central_ds.path
        )
        for res in central_ds.search(query):
            yield res
        return
    else:
        raise


@build_doc
class Search(Interface):
    """Search a dataset's metadata.

    Search capabilities depend on the amount and nature of metadata available
    in a dataset. This can include metadata about a dataset as a whole, or
    metadata on dataset content (e.g. one or more files). One dataset can also
    contain metadata from multiple subdatasets (see the 'aggregate-metadata'
    command), in which case a search can discover any dataset or any file in
    of these datasets.

    A search index is automatically built from the available metadata of any
    dataset or file, and a schema for this index is generated dynamically, too.
    Consequently, the search index will be tailored to data provided in a
    particular collection of datasets.

    Metadata fields (and possibly also values) are typically defined terms
    from a controlled vocabulary. Term definitions are accessible via the
    --show-keys flag.

    DataLad's search is built on the Python package 'Whoosh', which provides
    a powerful query language. Links to a description of the language and
    particular feature can be found below.

    Here are a few examples. Basic search::

      % datalad search searchterm

    Search for a file::

      % datalad search searchterm type:file

    Show definitions of search keys/fields::

      % datalad search --show-keys
        @id (unique identifier of an entity)
        dcterms:rights (http://purl.org/dc/terms/rights)
        duration(s) {'unit (http://purl.obolibrary.org/obo/UO_0000000)': 'http://purl.obolibrary.org/obo/UO_0000010', '@id': 'https://www.w3.org/TR/owl-time/#Duration'}
        name (http://schema.org/name)
        ...

    *Performance considerations*

    For dataset collections with many files (100k+) generating a comprehensive
    search index comprised of documents for datasets and individual files can
    take a considerable amount of time. If this becomes an issue, search index
    generation can be limited to a particular type of document (see the
    'metadata --reporton' option for possible values). The configuration
    setting 'datalad.metadata.searchindex-documenttype' will be queried on
    search index generation. It is recommended to place an appropriate
    configuration into a dataset's configuration file (.datalad/config)::

      [datalad "metadata"]
        searchindex-documenttype = datasets

    .. seealso::
      - Description of the Whoosh query language:
        http://whoosh.readthedocs.io/en/latest/querylang.html)
      - Description of a number of query language customizations that are
        enabled in DataLad, such as, querying multiple fields by default and
        fuzzy term matching:
        http://whoosh.readthedocs.io/en/latest/parsing.html#common-customizations
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
            doc="""search query using the Whoosh query language (see link to
            detailed description above). For simple queries, any number of search
            terms can be given as a list[CMD: (space-separated) CMD], and the
            query will return all hits that match all terms (AND) in any combination
            of fields (OR)."""),
        force_reindex=Parameter(
            args=("--reindex",),
            dest='force_reindex',
            action='store_true',
            doc="""force rebuilding the search index, even if no change in the
            dataset's state has been detected. This is mostly useful for
            developing new metadata support extensions."""),
        max_nresults=Parameter(
            args=("--max-nresults",),
            doc="""maxmimum number of search results to report. Setting this
            to 0 will report all search matches, and make searching substantially
            slower on large metadata sets.""",
            constraints=EnsureInt()),
        show_keys=Parameter(
            args=('--show-keys',),
            action='store_true',
            doc="""if given, a list of known search keys is shown (one per line).
            No other action is performed (except for reindexing), even if other
            arguments are given. Each key is accompanied by a term definition in
            parenthesis. In most cases a definition is given in the form
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
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query=None,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=20,
                 show_keys=False,
                 show_query=False):
        from whoosh import qparser as qparse

        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
            if ds.id is None:
                raise NoDatasetArgumentFound(
                    "This does not seem to be a dataset (no DataLad dataset ID "
                    "found). 'datalad create --force %s' can initialize "
                    "this repository as a DataLad dataset" % ds.path)
        except NoDatasetArgumentFound:
            for r in _search_from_virgin_install(dataset, query):
                yield r
            return

        # where does the bunny have the eggs?
        index_dir = opj(ds.path, get_git_dir(ds.path), 'datalad', 'search_index')

        idx_obj = _get_search_index(
            index_dir, ds, force_reindex)

        if show_keys:
            definitions_fname = opj(
                index_dir,
                'datalad_term_definitions.json.gz')
            try:
                defs = jsonload(gzopen(definitions_fname))
            except Exception as e:
                lgr.warning(
                    'No term definitions found alongside search index: %s',
                    exc_str(e))
                defs = {}

            for k in idx_obj.schema.names():
                print('{}{}'.format(
                    k,
                    ' {}'.format(
                        defs[k] if isinstance(defs[k], dict) else '({})'.format(
                            defs[k])) if k in defs else ''))
            return

        if not query:
            return

        with idx_obj.searcher() as searcher:
            # parse the query string, default whoosh parser ATM, could be
            # tailored with plugins
            parser = qparse.MultifieldParser(
                idx_obj.schema.names(),
                idx_obj.schema)
            # XXX: plugin is broken in Debian's whoosh 2.7.0-2, but already fixed
            # upstream
            parser.add_plugin(qparse.FuzzyTermPlugin())
            parser.add_plugin(qparse.GtLtPlugin())
            # replace field defintion to allow for colons to be part of a field's name:
            parser.replace_plugin(qparse.FieldsPlugin(expr=r"(?P<text>[()<>:\w]+|[*]):"))
            # for convenience we accept any number of args-words from the
            # shell and put them together to a single string here
            querystr = ' '.join(assure_list(query))
            # this gives a formal whoosh query
            wquery = parser.parse(querystr)

            if show_query:
                print(wquery)
                return
            # perform the actual search
            hits = searcher.search(
                wquery,
                terms=True,
                limit=max_nresults if max_nresults > 0 else None)
            # cheap way to get an approximate number of hits, without an expensive
            # scoring of all items
            # disabled: unreliable estimate, often confusing
            #nhits = hits.estimated_min_length()
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
            for hit in hits:
                res = dict(
                    action='search',
                    status='ok',
                    logger=lgr,
                    refds=ds.path,
                    # normpath to avoid trailing dot
                    path=normpath(opj(ds.path, hit['path'])),
                    query_matched={assure_unicode(k): assure_unicode(v)
                                   if isinstance(v, unicode_srctypes) else v
                                   for k, v in hit.matched_terms()},
                    metadata={k: v for k, v in hit.fields().items()
                              if k not in ('path', 'parentds')})
                if 'parentds' in hit:
                    res['parentds'] = normpath(opj(ds.path, hit['parentds']))
                yield res
                nhits += 1

            if max_nresults and nhits == max_nresults:
                lgr.info(
                    "Reached the limit of {}, there could be more which "
                    "were not reported.".format(topstr)
                )