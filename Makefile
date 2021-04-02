paper.pdf: paper.md paper.bib
	datalad containers-run --explicit openjournals-paperdraft

.PHONY: pandoc
pandoc: paper.md paper.bib
	./build.sh
