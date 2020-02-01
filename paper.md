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

# Summary

... should include Statement of Need

![DataLad: overview of available commands for various parts of the data management process](figures/datalad_process.png)


## Modular composition

![YODA: provenance of all data and computing environments from data to publication](figures/repronim-containers-yoda-lower.png)

## Execution provenance tracking



## Documentation

[DataLad Handbook](http://handbook.datalad.org) provide novices and advanced users of all backgrounds with a guide through both the basics of DataLad and start-to-end use cases of specific applications. [docs.datalad.org](http://docs.datalad.org/en/latest/) provides developers oriented information and detailed description of command line and Python interfaces.

# DataLad Ecosystem

... should mention any past or ongoing research projects using the software and recent scholarly publications enabled by it.

## Extensions

DataLad provides mechanism for providing domain or technology specific extensions.
Notable extensions at the moment are
- [datalad-container](https://github.com/datalad/datalad-container)
- [datalad-neuroimaging](https://github.com/datalad/datalad-neuroimaging)
The same mechanism is used for rapid development of new functionality to later be moved into the main DataLad codebase 
(e.g., [datalad-metalad](https://github.com/datalad/datalad-metalad/))

## Integrations

[ReproMan](http://reproman.repronim.org) integrates with DataLad to provide
[OpenNeuro](http://openneuro.org) is using DataLad for data logistics with data deposited to a public S3 bucket.

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

DataLad development is supported in part by 
NSF [1429999](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1429999), 
[1912266](http://www.nsf.gov/awardsearch/showAward?AWD_ID=1912266) 
(PI: Halchenko) and BMBF 01GQ1411 and 01GQ1905 (PI: Hanke) 
through [CRCNS](https://www.nsf.gov/funding/pgm_summ.jsp?pims_id=5147) program; 
ReproNim project NIH [1P41EB019936-01A1](https://projectreporter.nih.gov/project_info_details.cfm?aid=8999833&map=y).



# References