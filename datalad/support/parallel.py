# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for parallel execution

"""

__docformat__ = 'restructuredtext'

import datetime as dt
import humanize
import inspect
import uuid
from collections import defaultdict

from ..log import log_progress
from .iterators import IteratorWithAggregation

from . import ansi_colors as colors


def _count_str(count, verb, omg=False):
    if count:
        msg = "{:d} {}".format(count, verb)
        if omg:
            msg = colors.color_word(msg, colors.RED)
        return msg


def producer_consumer(
        producer, consumer,
        label="Total", unit="items",
        lgr=None,
        # TODO: actually parallel
        # njobs=None,
        # order="as-complete",  # "original", anything else?
):
    """

    Parameters
    ----------
    """

    pid = str(uuid.uuid4())  # could be based on PID and time may be to be informative?
    base_label = label
    if lgr is None:
        from .. import lgr

    # TODO: code is based on @with_result_progress . for now we will just keep it centered
    # around processing "our" return records, but IMHO it should be made more flexible
    # so the same machinery could be used for any function
    counts = defaultdict(int)

    log_progress(lgr.info, pid,
                 "%s: starting", label,
                 #will become known only later total=len(items),
                 label=label, unit=" " + unit)
    # TODO: in principle is not needed if producer is not a generator, and we could just take __len__
    # but to simplify the logic we will just always use it for now
    class Count:
        def __init__(self):
            self.n = 0
        def __call__(self, item, _=None):
            self.n += 1
            return item

    count = Count()
    it = IteratorWithAggregation(producer, count)
    producer_finished = False
    t0 = dt.datetime.now()
    for item in it:
        if not producer_finished and it.finished:
            producer_finished = True
            log_progress(
                lgr.info,
                pid,
                None,  # I do not think there is something valuable to announce
                total=count.n,
                update=0  # not None, so it does not stop
            )
        res = consumer(item)

        if inspect.isgeneratorfunction(consumer):
            ress = res
        else:
            ress = [res]

        for res in ress:
            counts[res["status"]] += 1
            count_strs = (_count_str(*args)
                          for args in [(counts["notneeded"], "skipped", False),
                                       (counts["error"], "failed", True)])
            if counts["notneeded"] or counts["error"]:
                label = "{} ({})".format(
                    base_label,
                    ", ".join(filter(None, count_strs)))

            log_progress(
                lgr.error if res["status"] == "error" else lgr.info,
                pid,
                "%s: processed result%s", base_label,
                " for " + res["path"] if "path" in res else "",
                label=label, update=1, increment=True)
            yield res
    log_progress(lgr.info, pid, "%s: done", base_label)
    # ??? how to make it leave the final record "automagically" or there is no such thing
    # so will log manually
    lgr.info("Finished processing %d %s which started %s", count.n, unit,
             # needs fresh humanize, 2.3.0-1 did not have it
             # humanize.precisedelta(dt.datetime.now() - t0),
             humanize.naturaltime(dt.datetime.now() - t0)
             )
