---
title: 'DataLad: data management system for discovery, management, and publication of digital objects of science'
tags:
  - Python
  - version control
  - data management
  - data provenance
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
date: 1 February 2020
bibliography: paper.bib

---

# Summary

The DataLad project (http://datalad.org) adapted the models of open-source software development and distribution to address technical limitations of today's data management, sharing, and provenance collection.
Born of idea to provide a unified data distribution for neuroscience, taking a versatile system for data logistics 
(git-annex, https://git-annex.branchable.com) built on top of the most popular distributed version control system 
(git, https://git-scm.com), and adopting ideas and procedures from software distributions, DataLad delivers a completely open, pioneering platform for flexible distributed research data management (dRDM) [@Hanke_2021].

# Statement of Need

Code, data, and computing environments are at the core of scientific practice, and unobstructed access and efficient management of all those digital objects promotes scientific discovery through collaboration, reproducibility, and replicability. 
While code management and sharing is streamlined with the advance of software distributions, distributed version control systems, and social coding portals like GitHub, data has remained a “2nd-class citizen” in the contemporary scientific process, despite FAIR principles postulating demands on public data hosting portals and the big callout for Data Science.
Disconnected FAIR data hosting portals provide a cacophony of data access and authentication methods, data versioning is frequently ignored, and shared data provenance is often not recoverable simply because data management is rarely considered to be an integral part of the scientific process.

## Why git and git-annex

Git is an excellent distributed content management system geared toward management and collaboration on text files, and as such cannot handle large or binary files well.
Moreover, any data committed to git becomes available to all clones of that repository, thus making it hard or impossible to provide distributed storage of managed data, or revocation of individual files from distribution.  
Git-annex takes advantage of git for management of textual information to overcome git's limitation in management of individual files (be it a large data file or a sensitive data) content.
A file managed by git-annex is replaced with a symbolic link pointing to the content of the file as identified by its content checksum, and only such light-weight link is directly committed into git.
Git-annex then manages files availability information in any local repository, or other git remotes or external resources, e.g. web urls.
Such simple approach allows git-annex to scale to manage virtually arbitrarily large files, and "link" files in a git repository to vast data resources available online. 

## Why git and git-annex alone are not enough

Research workflows impose additional demands for an efficient research data management (RDM) platform besides "version control" and "data transport".
Many research datasets contain millions of files, and that precludes placing such datasets in their entirety within a single git repository even if files are tiny in their size.
Such datasets should be partitioned into smaller subdatasets (e.g., a subdataset per each subject in the dataset comprising thousands of participants).
Such modularization allows for not only scalable management, but also for efficient reuse of a selected subset of datasets.
DataLad uses standard "git submodules" mechanism to unambigously link individual datasets into larger super-datasets, and further simplifies working with such hierarchies of datasets.
DataLad makes it trivial to operate on individual files deep in the hierachy or entire sub-trees of datasets. 

A typical step of any empirical study requires two major components: input data (obtained from external resources or obtained from prior step) and processing code (ideally accompanied with an entire computational environment).
Given data and processing, it produces output results which in turn might become input to another step. 


# DataLad ecosystem

## DataLad core

`datalad` Python package provides both a Python library and a command line tool which expose core DataLad functionality to fulfill a wide range of dRDM use cases in any field of science.
Its API (see \autoref{fig:one}) operates on DataLad datasets which are just git (with optional git-annex for data) repositories with additional metadata and configuration.
 
Figure 1

![DataLad: overview of available commands for various parts of the data management process \label{fig:one}](figures/datalad_process.png)

Based on built-in mechanism of Git submodules, DataLad embraces and simplifies modular composition of smaller datasets into a larger (super)datasets.
With this simple paradigm, DataLad fulfills YODA principles (TODO) and facilitates efficient access, composition, scalability, reuse, sharing, and reproducibility of results.
As a testament of scalability, http://datasets.datalad.org provides a DataLad (super)dataset encapsulating thousands of datasets and providing a unified access to over 250 TBs of primarily neural data from a wide range of hosting portals. 

## Extensions

DataLad provides mechanism for providing domain or technology specific extensions.
Notable extensions at the moment are
- [datalad-container](https://github.com/datalad/datalad-container)
- [datalad-neuroimaging](https://github.com/datalad/datalad-neuroimaging)
The same mechanism is used for rapid development of new functionality to later be moved into the main DataLad codebase 
(e.g., [datalad-metalad](https://github.com/datalad/datalad-metalad/))

## Ecosystem

DataLad can be used as an independent tool, or as a core technology behind a larger platform.
[OpenNeuro](http://openneuro.org) uses DataLad for data logistics with data deposition to a public S3 bucket.
[CONP-PCNO](https://github.com/CONP-PCNO/) adopts aforementioned modular composition to deliver a rich collection of datasets with public or restricted access to data.
[ReproMan](http://reproman.repronim.org) integrates with DataLad to provide version control and data logistics 


## Datasets

DataLad datasets collections
- [http://datasets.datalad.org]() - a DataLad superdataset collating hundreds of datasets covering hundreds of TBs of largely neural data
- [https://github.com/datalad-datasets]() - interesting open data resources

## Documentation

DataLad core repository populates [docs.datalad.org](http://docs.datalad.org/en/latest/) with developers oriented information and detailed description of command line and Python interfaces. 
A comprehensive [DataLad Handbook](http://handbook.datalad.org) oriented toward novice and advanced users of all backgrounds is a separate project (https://github.com/datalad-handbook/).

## Development

`datalad` heavily relies on stability of underlying core tools - `git` and `git-annex`.
To guarantee 
Through its lifetime, DataLad project have been supporting development of `git-annex`.  

## Contributing

# Author Contributions

if desired/needed -- or drop altogether.

# Conflicts of interest

There are no conflicts to declare.

# Acknowledgements

DataLad development was made possible thanks to support by 
NSF [1429999](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1429999), 
[1912266](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1912266) 
(PI: Halchenko) and BMBF 01GQ1411 and 01GQ1905 (PI: Hanke) 
through [CRCNS](https://www.nsf.gov/funding/pgm_summ.jsp?pims_id=5147) program.
It received significant contributions from ReproNim [1P41EB019936-01A1](https://projectreporter.nih.gov/project_info_details.cfm?aid=8999833&map=y) and DANDI [5R24MH117295-02](https://projectreporter.nih.gov/project_info_description.cfm?aid=9981835&icde=53349087) NIH projects. ... .



# References
