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
  - name: Michael Hanke
    affiliation: "2, 3"
 - name: Adina Wagner
   orcid: 0000-0003-2917-3450
   affiliation: 2
 - Ben, Adina, ... are we adding all contributors?

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

# Statement of Need

Code, data, and computing environments are at the core of scientific practice, and unobstructed access and efficient management of all those digital objects promotes scientific discovery through collaboration, reproducibility, and replicability. 
While code management and sharing is streamlined with the advance of software distributions, distributed version control systems and social coding portals like GitHub, data has remained a “2nd-class citizen” in the contemporary scientific process, despite FAIR principles postulating demands on public data hosting portals and the big callout for Data Science.
Disconnected FAIR data hosting portals provide a cacophony of data access and authentication methods, data versioning is frequently ignored, and shared data provenance is often not recoverable simply because data management is rarely considered to be an integral part of the scientific process.

The DataLad project (http://datalad.org) adapted the models of open-source software development and distribution to address technical limitations of today's data management, sharing, and provenance collection.
By taking a versatile system for data logistics (git-annex) built on top of the most popular distributed version control system (git), and adopting ideas and procedures from software distributions, DataLad project delivers a completely open, pioneering platform for flexible distributed research data management (dRDM).

# Features

`datalad` Python package provides both a Python library and a command line tool   


![DataLad: overview of available commands for various parts of the data management process](figures/datalad_process.png)


## Modular composition

![YODA: provenance of all data and computing environments from data to publication](figures/repronim-containers-yoda-lower.png)

## Execution provenance tracking


## Documentation

[DataLad Handbook](http://handbook.datalad.org) provide novices and advanced users of all backgrounds with a guide through both the basics of DataLad and start-to-end use cases of specific applications. [docs.datalad.org](http://docs.datalad.org/en/latest/) provides developers oriented information and detailed description of command line and Python interfaces.

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

TODO: site dRDM paper

## Datasets

DataLad datasets collections
- [http://datasets.datalad.org]() - a DataLad superdataset collating hundreds of datasets covering hundreds of TBs of largely neural data
- [https://github.com/datalad-datasets]() - interesting open data resources

# Citations

Citations to entries in paper.bib should be in
[rMarkdown](http://rmarkdown.rstudio.com/authoring_bibliographies_and_citations.html)
format.

For a quick reference, the following citation commands can be used:
- `@author:2001`  ->  "Author et al. (2001)"
- `[@author:2001]` -> "(Author et al., 2001)"
- `[@author1:2001; @author2:2001]` -> "(Author1 et al., 2001; Author2 et al., 2002)"

# Figures

Figures can be included like this: ![Example figure.](figure.png)

# Acknowledgements

DataLad development was made possible thanks to support by 
NSF [1429999](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1429999), 
[1912266](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1912266) 
(PI: Halchenko) and BMBF 01GQ1411 and 01GQ1905 (PI: Hanke) 
through [CRCNS](https://www.nsf.gov/funding/pgm_summ.jsp?pims_id=5147) program.
It was further enhanced through contributions by ReproNim project NIH [1P41EB019936-01A1](https://projectreporter.nih.gov/project_info_details.cfm?aid=8999833&map=y), DANDI (TODO), ... .



# References