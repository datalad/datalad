# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Nodes for the pipelines.

Each node must be a callable accepting data, and must yield (thus be a generator)
"derived" data.  Many nodes, despite being classes, named in lower case for uniform
appearance within pipeline definitions.  Some (e.g. Sink) uses typical aggreement on
camel casing class names -- such nodes are typically instantiated outside of the
pipeline definition so they could be retrospected later on
"""

"""
Many nodes feel like class is a bit too heavy for them since by relying on
"""
