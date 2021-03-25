paper.pdf: paper.md paper.bib
	datalad containers-run --explicit openjournals-paperdraft
