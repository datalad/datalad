#!/bin/bash
#
# Compile and build Markdown paper into PDF
#
# Adopted from http://github.com/lzkelley/kalepy/
#
# Dependencies
#  sudo apt-get install pandoc-citeproc pandoc
# -------------------------------------------------------------------------------------------------

INPUT_TXT="paper.md"
INPUT_BIB="paper.bib"
OUTPUT_PDF="paper.pdf"
ENGINE="xelatex"
# OPTS="-V geometry:margin=1in --variable classoption=twocolumn"
OPTS="-V geometry:margin=1in"

#pandoc --citeproc ${OPTS} --bibliography=${INPUT_BIB} --pdf-engine=${ENGINE} -s ${INPUT_TXT} -o ${OUTPUT_PDF}
pandoc --filter pandoc-citeproc --bibliography=${INPUT_BIB} --pdf-engine=${ENGINE} -s ${INPUT_TXT} -o ${OUTPUT_PDF}
