---
title: 'DataLad: decentralized research data management system'
tags:
  - Python
  - command line
  - version control
  - data management
  - data distribution
  - data provenance
  - reproducibility
authors:
 - name: Yaroslav O. Halchenko
   orcid: 0000-0003-3456-2493
   affiliation: 1
 - name: Adina Wagner
   orcid: 0000-0003-2917-3450
   affiliation: 2
 - name: Michael Hanke
   orcid: 0000-0001-6398-6370
   affiliation: "2, 3"
affiliations:
 - name: Dartmouth College, Hanover, NH, United States
   index: 1
 - name: Institute of Neuroscience and Medicine, Brain & Behaviour (INM-7), Research Centre Jülich, Jülich, Germany
   index: 2
 - name: Institute of Systems Neuroscience, Medical Faculty, Heinrich Heine University Düsseldorf, Düsseldorf, Germany
   index: 3
date: 24 March 2021
bibliography: paper.bib

---

# Summary

The DataLad project (http://datalad.org) adapted the models of open-source software development and distribution to address technical limitations of today's data management, sharing, and provenance collection.
Born from the idea to provide a unified data distribution for neuroscience, taking a versatile system for data logistics
(git-annex, https://git-annex.branchable.com) built on top of the most popular distributed version control system 
(Git, https://git-scm.com), and adopting ideas and procedures from software distributions, DataLad delivers a completely open, pioneering platform for flexible decentralized research data management (dRDM) [@Hanke_2021].

# Statement of Need

Code, data, and computing environments are at the core of scientific practice, and unobstructed access and efficient management of all those digital objects promotes scientific discovery through collaboration, reproducibility, and replicability. 
While software development and sharing are streamlined with the advance of software distributions, distributed version control systems, and social coding portals like GitHub, data have remained a “2nd-class citizen” in the contemporary scientific process, despite FAIR principles [@FAIR2016] postulating demands on public data hosting portals and the big callout for Data Science.
Disconnected data hosting portals provide a cacophony of data access and authentication methods, data versioning is frequently ignored, and shared data provenance <!-- what is "shared data provenance"? --><!-- BEN: may be: data provenance - if shared at all - is often not ... --> is often not recoverable simply because data management is rarely considered to be an integral part of the scientific process.
<!-- MIH summary: inconvenient access, version/provenenance information unavailable -->
DataLad aims to solve these issues by streamlining data consumption, publication, and updating routines, by providing a simplified core API <!--BEN: s/core API/interface/ while I don't mind using "API" internally I don't think it's appropriate in a publication. It's just an interface, not really an application programming interface. --> for Git and git-annex operations, and by providing additional features for reproducible science such as command execution provenance capturing and automatic recomputation based on complete process provenance.
Since it is interoperable with a large variety of scientific and commercial hosting services and available for all operating systems,
DataLad can be integrated into established systems with minimal adjustments.

## Why Git and git-annex

Git is an excellent <!-- citation needed -->distributed content management system geared towards managing and collaborating on text files <!-- citation needed, does not match self-description -->, but it is not designed to handle large (e.g., over a gigabyte) or binary files efficiently.
Moreover, any data committed to Git becomes available to all clones of that repository. In the context of scientific data, this makes it hard or impossible to provide distributed storage of managed data <!-- why? individual tailoring is hard, but distribution not, what is special about scientific data in this regard? -->, or revoke individual files <!-- this somewhat suggests, that with datalad one can easily revoke, which at least requires a clarification of that does and doesn't mean -->, such as accidentally stored personal data or data from participants that withdrew from a study.
Git-annex takes advantage of Git's ability to manage textual information to overcome Git's limitation in managing individual file content that is either large or sensitive.
File content managed by git-annex is placed into an annex, and in its place, git-annex commits a link (a symbolic link or a git link) pointing to the content of the file into Git.
The content representation is based on a checksum of the file's content.
As such, while only a light-weight link is directly committed into Git, this committed information contains the content identity of annexed files.
Git-annex then manages files availability information in any local repository, other Git remotes, or external resources, e.g. web urls.
Having that information, git-annex takes care of all transport logistics to exchange data upon user request.
Such simple approach allows git-annex to scale to manage and version control virtually arbitrarily large files, and "link" files in a Git repository to vast data resources available online.
<!-- BEN thinks we need to make explicit the idea, that by means of how annex
works, the content and access control to it is separated from the version
control (and metadata). ATM this follows implicitly but may be much less obvious
to someone who didn't dive into it yet -->

## Why Git and git-annex alone are not enough

<!-- this is "what does datalad add to Git+git-annex -->
<!-- MIH thinks: #1 nesting, #2 reproducible execution, #3 additional software adaptors for concrete services relevant for science -->

**They are generic and might lack support for domain specific solutions.** 
Git can interact with other repositories on the file system or accessible via a set of standard (ssh, http) or custom (Git) network transport protocols.
Interaction with non git-aware portals should then be implemented via custom Git transfer protocols, as it e.g. was done in datalad-osf [@datalad-osf:zenodo].
Git-annex provides access to a wide range of external data storage resources via various protocols, but cannot implement all idiosyncracies of any individual data portal.
In particular, scientific data is frequently stored in compressed archives to reduce its storage demands, or on specialized servers, such as XNAT (www.xnat.org).
To address these demands, git-annex implemented support for external special remotes by establishing a protocol [@git-annex:special_remotes_protocol] through which external tools can provide custom transport functionality transparently to the user.
This allowed DataLad and many other projects to facilitate access to an ever growing collection of resources [@git-annex:special_remotes] and to overcome technological limitations (e.g., maximal file sizes, or file system inodes limits).

**They require a layer above to establish a *distribution*.**
The DataLad project's initial goal was to provide a data distribution with unified access to the already available public data archives in neuroscience, such as http://crcns.org or http://openfmri.org.
Git and git-annex are just "client tools" and do not provide aggregation of different resources into a unified distribution on their own.
http://datasets.datalad.org became an example of such a data distribution curated by the DataLad team, which at the moment provides streamlined access to over 250 TBs of data across wide range of projects and archives.
<!-- MIH thinks this needs a clarification of terms. If datasets.d.o is a distribution than datalad is "just a client tool" too. I think this is probably aimed at the nesting feature, and if so, we should use the term, because people can read about it in the handbook. This technical feature is then what is used to build a "unified data distribution"-->
<!-- BEN adds to MIH: below we call ds.dl.org a testament of scalability, and
this is what I think it is. A showcase, not somehow a central or special part of
DataLad itself. Therefore I'd present it as the conclusion of what that
modularization allows for. Overall the "additional layer" the headline talks
about is not clear to me.-->

**Modularization is needed to scale.**
Research workflows impose additional demands for an efficient research data management (RDM) platform besides "version control" and "data transport".
Many research datasets contain millions of files, and that precludes placing such datasets in their entirety within a single Git repository even if individual files are tiny in their size.
Such datasets should be partitioned into smaller subdatasets (e.g., a subdataset per each subject in the dataset comprising thousands of participants).
This modularization allows for not only scalable management <!-- unclear how management of 10k small pieces becomes more scalable than one piece with 10k parts -->, but also for the efficient reuse of a selected subset of datasets.
DataLad uses Git's submodule mechanism to unambiguously link (versions of) individual datasets into larger super-datasets, and further simplifies working with the resulting hierarchies of datasets with recursive operations across dataset boundaries.
<!-- BEN: There are more aspect of modularization than reuse and large-scale.
Most importantly, that's the notions of dependencies and a derivative
relationsship that can be expressed that way, I think. --> 
With this, DataLad makes it trivial to operate on individual files deep in the hierarchy or entire sub-trees of datasets, providing a "mono-repo"-like user experience in datasets nested arbitrarily deep.
<!-- modularization is presented as #2, but it seems to be just #1 (nesting) described from a different angle -->

**They do not necessarily facilitate the best scientific workflow.**
Git and git-annex, being generic tools, come with rich interfaces and allow for a wide range of workflows.
DataLad strives to provide a higher level interface to more efficiently cover typical use cases encountered in the scientific practice than the direct invocation of individual Git and git-annex commands, and to encourage efficient computation and reproducible workflows.
To this end, DataLad is also accompanied by rich documentation [@datalad-handbook:zenodo] to guide a scientist of any technological competency level, and agnostic of the field of science.
<!-- key point thinks MIH: to some degree the handbook also "just" shows how to use git/git-annex to implement concrete processes that are of relevance for science. In some what "figuring out how to do it with git/git-annex is a major contribution, some of it implemented in code (simplified/alternative API), but otherwise written up in English -->

# Overview of the DataLad and its ecosystem

## DataLad core

The `datalad` Python package provides both a Python library and a command line tool which expose core DataLad functionality to fulfill a wide range of dRDM use cases for any domain.
Its API (see \autoref{fig:one}) operates on DataLad datasets which are just Git (with optional git-annex for data) repositories with additional metadata and configuration.
 
![DataLad: overview of available commands for various parts of the data management process \label{fig:one}](figures/datalad_process.png)

Using Git's submodules mechanism, DataLad embraces and simplifies modular composition of smaller datasets into larger (super)datasets.
With this simple paradigm, DataLad fulfills the YODA principles for reproducible science [@yoda:myyoda] and facilitates efficient access, composition, scalability, reuse, sharing, and reproducibility of results  (see Figure 2).

![DataLad datasets all the way down: from publication to raw data](figures/datalad-nesting-access.png)

As a testament of scalability, http://datasets.datalad.org provides a DataLad (super)dataset encapsulating thousands of datasets and providing unified access to over 250 TBs of primarily neural data from a wide range of hosting portals. 

## Extensions

Similarly to Git and git-annex, DataLad core strives to provide a generic tool, not encumbered by a specific field of science or domain.
To harmoniously extend its functionality, DataLad provides mechanism for providing domain or technology specific extensions.
Some exemplar extensions include:

- [datalad-container](https://github.com/datalad/datalad-container) [@datalad-container:zenodo] to simplify management and use of Docker and Singularity containers typically containing complete computational environments;
- [datalad-crawler](https://github.com/datalad/datalad-crawler) [@datalad-crawler:zenodo] the functionality which initiated the DataLad project - support for creating and updating DataLad datasets from external resources;
- [datalad-neuroimaging](https://github.com/datalad/datalad-neuroimaging) [@datalad-neuroimaging:zenodo] to provide neuroimaging specific procedures and metadata extractors
- [datalad-osf](https://github.com/datalad/datalad-osf/) [@datalad-osf:zenodo] to collaborate using DataLad through the Open Science Framework (OSF).

The same mechanism of extensions is used for rapid development of new functionality to later be moved into the main DataLad codebase 
(e.g., [datalad-metalad](https://github.com/datalad/datalad-metalad/)).
https://github.com/datalad/datalad-extensions/ repository provides a list of extensions and contineous integration testing of their released versions against released and development versions of the DataLad core. 
A premade template (https://github.com/datalad/datalad-extension-template) can be used for creating new DataLad extensions.

## External uses and integrations

TODO: probably here cite some examples of scientific papers in the wild which used DataLad

DataLad can be used as an independent tool, or as a core technology behind a larger platform.
[OpenNeuro](http://openneuro.org) uses DataLad for data logistics with data deposition to a public S3 bucket.
[CONP-PCNO](https://github.com/CONP-PCNO/) adopts aforementioned modular composition to deliver a rich collection of datasets with public or restricted access to data.
[ReproMan](http://reproman.repronim.org) integrates with DataLad to provide version control and data logistics.
https://www.datalad.org/integrations.html provides a more complete list of DataLad usage and integration with other projects, and @Hanke_2021 provides a systematic depiction of DataLad as a dRDM used by a number of projects. 


## Documentation

The DataLad core repository populates [docs.datalad.org](http://docs.datalad.org/en/latest/) with developer-oriented information and detailed descriptions of command line and Python interfaces.
A comprehensive [DataLad Handbook](http://handbook.datalad.org) [@datalad-handbook:zenodo] provides documentation with numerous usage examples oriented toward novice and advanced users of all backgrounds.

The simplest "prototypical" example is `datalad search haxby` which would install the http://datasets.datalad.org superdataset, and search for datasets mentioning `haxby` anywhere in their metadata records.
Any reported dataset could be immediately installed using `datalad install` command, and data files of interest obtained using `datalad get`.
More use-case driven examples could be found in [@datalad-handbook:use-cases].

## Installation

The DataLad Handbook provides [installation instructions](http://handbook.datalad.org/en/latest/intro/installation.html) for all operating systems.
DataLad releases are distributed through PyPI, Debian, NeuroDebian, brew, conda-forge.
The [datalad-installer](https://github.com/datalad/datalad-installer/) (also available from PyPI) can be used to streamline the installation of `git-annex`, which cannot be installed via `pip` and thus may need a separate installation on some operating systems.

## Development

DataLad is being developed openly in a public repository (https://github.com/datalad/datalad) since its inception in 2013.
At the time of this publication, the repository amassed over 13.5k commits, 2.5k merged PRs, and 2.3k closed (+700 open) issues from over 30 contributors.
Issue tracker, labels, milestones, and pull requests (from personal forks) are used to coordinate development.
DataLad heavily relies on the versatility and stability of the underlying core tools - Git and git-annex.
To avoid reimplementing the wheel and to benefit the git-annex user community at large, many aspects of the desired functionality are and have been implemented directly in git-annex through collaboration with the git-annex developer Joey Hess (see https://git-annex.branchable.com/projects/datalad).
To guarantee robust operation across various deployments DataLad heavily utilizes continuous integration platforms (Appveyor, GitHub actions, and Travis CI) for testing DataLad core, building and testing git-annex (in a dedicated https://github.com/datalad/git-annex), and integration testing 
with DataLad extensions (https://github.com/datalad/datalad-extensions/).

## Contributions

DataLad is released under DFSG- and OSI-compliant MIT/Expat license, and license terms for reused in the code-base components are provided in the [COPYING](https://github.com/datalad/datalad/blob/master/COPYING) file.
[CONTRIBUTING.md](https://github.com/datalad/datalad/blob/master/CONTRIBUTING.md) file shipped within DataLad's source repository provides guidelines for submitting contributions.

# Author Contributions

if desired/needed -- or drop altogether.

# Conflicts of interest

There are no conflicts to declare.

# Acknowledgements

DataLad development was facilitated by a senior adviser Dr. James V. Haxby (Dartmouth College), and made possible thanks to support by
NSF [1429999](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1429999), 
[1912266](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1912266) 
(PI: Halchenko) and BMBF 01GQ1411 and 01GQ1905 (PI: Hanke) 
through [CRCNS](https://www.nsf.gov/funding/pgm_summ.jsp?pims_id=5147) program.
It received significant contributions from ReproNim [1P41EB019936-01A1](https://projectreporter.nih.gov/project_info_details.cfm?aid=8999833&map=y) and DANDI [5R24MH117295-02](https://projectreporter.nih.gov/project_info_description.cfm?aid=9981835&icde=53349087) NIH projects. ... .
We would also like to express our gratitude to [TODOADD: contributors not among co-authors]... for the contributions to the codebase, and [TODOADD: notable contributors to issues] for filing bug reports and recommendations.


# References
