#!/usr/bin/env python3

import argparse
from Bio import SeqIO


def load_locus_tags(locus_file):
    """Load locus tags from a text file, one per line."""
    with open(locus_file, "r") as f:
        return {line.strip() for line in f if line.strip()}


def strand_to_symbol(strand):
    """Convert Biopython strand value to +, -, or ."""
    if strand == 1:
        return "+"
    elif strand == -1:
        return "-"
    else:
        return "."


def extract_locus_positions(genbank_file, locus_tags, output_file):
    with open(output_file, "w") as out:
        for record_index, record in enumerate(SeqIO.parse(genbank_file, "genbank"), start=1):
            for feature in record.features:
                if feature.type != "CDS":
                    continue

                if "locus_tag" not in feature.qualifiers:
                    continue

                locus_tag = feature.qualifiers["locus_tag"][0]

                if locus_tag not in locus_tags:
                    continue

                start = int(feature.location.start) + 1   # convert 0-based to 1-based
                end = int(feature.location.end)           # Biopython end is already correct for 1-based closed interval
                strand = strand_to_symbol(feature.location.strand)

                out.write(f"{locus_tag}\t{start}\t{end}\t{strand}\t{record_index}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate lociLocations.txt from a GenBank file and list of loci."
    )
    parser.add_argument("-g", "--genbank", required=True, help="Input GenBank file")
    parser.add_argument("-l", "--locus_tags", required=True, help="Text file of locus_tags, one per line")
    parser.add_argument("-o", "--output", required=True, help="Output TSV file (headerless)")
    args = parser.parse_args()

    locus_tags = load_locus_tags(args.locus_tags)
    extract_locus_positions(args.genbank, locus_tags, args.output)


if __name__ == "__main__":
    main()