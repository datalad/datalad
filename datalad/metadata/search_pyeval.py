# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from time import time

from datalad.dochelpers import exc_str, single_or_plural
from datalad.metadata.metadata import query_aggregated_metadata
from datalad.metadata.search import lgr
from datalad.metadata.search_base import _Search
from datalad.utils import assure_list


class _PyEvalSearch(_Search):
    """A search engine which consumes a query
    which is a Python code to be evaluated in an environment where metadata
    keys are provided as variables (@id -> id).
    """
    _mode_label = 'pyeval'
    _default_documenttype = 'datasets'

    # def __init__(self, ds, **kwargs):
    #     super(_PyEvalSearch, self).__init__(ds, **kwargs)
    #     #self._queried_keys = None  # to be memoized by get_query

    # TODO: I feel that we need some base class/mixin like a
    #  _LoopySearch which would implement this main loop in a single location
    #  with uniform treatment of metadata (adding those fields into doc etc)
    # TODO2: that loop whould be two nested dataset/files so we could
    #  quickly exit whenever enough per dataset (e.g. 1) found
    def __call__(self, query, max_nresults=None, full_record=True):
        query = assure_list(query)
        if max_nresults is None:
            # no limit by default
            max_nresults = 0
        # separate ones are considered to be independent clauses for "and"
        composite_query = ' and '.join(['(%s)' % q for q in query])
        composite_query_ = compile(composite_query, 'query', 'eval')

        def matcher(doc):
            try:
                return eval(composite_query_, {}, doc)
            except (KeyError, NameError) as exc:
                # lgr.debug("Something was missing in the record -- should be generally ok")
                # TODO: record if ANY matching resulted in not hitting this.
                #  If not -- we must have misspecified something, and should
                #  alert user similarly to get_nohits_msg of egrep.
                #  So -- we need smth like _queried_keys here as well
                pass
            except Exception as exc:
                # TODO: we could analyze each part of composite_query independently
                # (if len(query) > 1) to provide a more specific pointer to what part
                # has caused a failure
                lgr.info("Failed to match %s: %s", query, exc_str())

        nhits = 0
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
            # produce a flattened metadata dict to search through
            doc = meta.copy() #RF _meta2autofield_dict(meta, val2str=True, consider_ucn=consider_ucn)
            # inject a few basic properties into the dict
            # analog to what the other modes do in their index
            doc.update({
                # RF: @ replacement specific to here
                k.replace('@', ''): res[k] for k in ('@id', 'type', 'path', 'parentds')
                if k in res})
            # use search instead of match to not just get hits at the start of the string
            # this will be slower, but avoids having to use actual regex syntax at the user
            # side even for simple queries
            # DOTALL is needed to handle multiline description fields and such, and still
            # be able to match content coming for a later field
            lgr.log(7, "Querying %s among %d items", query, len(doc))
            t0 = time()
            is_a_match = matcher(doc)
            dt = time() - t0
            lgr.log(7, "Finished querying in %f sec", dt)
            # The rest below seemed to be specific to the grep one, although
            # TODO: check exactly what was intended
            # # retain what actually matched
            # matched = {k[1]: match.group() for k, match in matches.items() if match}
            # # implement AND behavior across query expressions, but OR behavior
            # # across queries matching multiple fields for a single query expression
            # # for multiple queries, this makes it consistent with a query that
            # # has no field specification
            # if matched and len(query) == len(set(k[0] for k in matches if matches[k])):
            if is_a_match:
                hit = dict(
                    res,
                    action='search',
                    # query_matched=matched,
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