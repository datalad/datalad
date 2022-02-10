#!/usr/bin/env python3
# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Little helper to copy all URLs which were mistakenly submitted to datalad
remote instead of straight to web.

May be later could be RFed into some helper function if comes needed again
"""

from collections import defaultdict
from datalad.support.annexrepo import AnnexRepo
from datalad import lgr
from tqdm import tqdm


def get_remote_urls(rec, remote):
    for k, v in rec.items():
        if v.get('description', '') in [remote, '[%s]' % remote]:
            return v.get('urls', [])
    return []

if __name__ == '__main__':
    annex = AnnexRepo('.', create=False, init=False)
    # enable datalad special remote
    urls_to_register = defaultdict(list)  # key: urls
    try:
        annex.call_annex(["enableremote", "datalad"])
        # go through each and see where urls aren't yet under web
        # seems might have also --in=datalad to restrict
        w = annex.whereis([], options=['--all'], output='full')
        lgr.info("Got %d entries", len(w))
        for k, rec in tqdm(w.items()):
            datalad_urls = get_remote_urls(rec, 'datalad')
            web_urls = set(get_remote_urls(rec, 'web'))
            for url in datalad_urls:
                if url not in web_urls:
                    if 'openneuro.s3' in url or 'openfmri.s3' in url:
                        urls_to_register[k].append(url)
                    else:
                        lgr.warning("Found unexpected url %s" % url)

    finally:
        # disable datalad special remote
        annex.remove_remote("datalad") # need to disable it first
    lgr.info(
        "Got %d entries which could get new urls",
        len(urls_to_register)
    )
    for k, urls in tqdm(urls_to_register.items()):
        for url in urls:
            annex.call_annex([
                "registerurl", '-c', 'annex.alwayscommit=false', k, url])
    # to cause annex to commit all the changes
    annex.call_annex(["merge"])
    annex.gc(allow_background=False)
