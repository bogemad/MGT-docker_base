#!/usr/bin/env python3
"""
extract_alleles.py

Batch driver for running Reads2MGTAlleles through the Docker wrapper
(./scripts/reads_to_alleles.py) with auto-mount detection.

It reads allele_file_details.tsv (TSV with: strainid <tab> files) and
runs the pipeline for each sample. Input files are expected to exist
on the host filesystem; the wrapper will detect and mount their parent
directories automatically.

Outputs are written into --out_dir.

Example:
  ./scripts/extract_alleles.py \
      --source_dir /path/to/my/files \
      --out_dir /path/to/upload_later \
      --species_key Appname
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import ast
import json
from pathlib import Path
import importlib.util
from dotenv import load_dotenv

REPO_BASE = Path(__file__).resolve().parents[1]
DOTENV = REPO_BASE / ".env"
load_dotenv(DOTENV)

DETAILS_FILE = REPO_BASE / "data" / "allele_file_details"
WRAPPER = REPO_BASE / "scripts" / "reads_to_alleles.py"
SETTINGS = REPO_BASE / "Mgt" / "Mgt" / "Mgt" / "settings.py"
REF_ALLELES = REPO_BASE / "species_specific_alleles" / f"{os.getenv("APPNAME")}_intact_alleles.fasta"
ALLELES_DIR = REPO_BASE / "data" / "alleles"
PATHOVAR_KEY = REPO_BASE / "mlst" / "mlst_pathovar_key.txt"
SPECIES_JSON = REPO_BASE / "Mgt" / "Mgt" / "MGT_processing" / "Reads2MGTAlleles" / "rtoa_defaults.json"

FASTQ = {".fastq", ".fq"}
FASTA = {".fasta", ".fa", ".fna"}

def strip_gz(p: Path) -> Path:
    return Path(p.stem) if p.suffix.lower() == ".gz" else p

def infer_intype(paths):
    exts = {strip_gz(Path(p)).suffix.lower() for p in paths}
    if len(paths) == 2:
        return "reads"
    if len(paths) == 1:
        if exts & FASTA:
            return "genome"
        if exts & FASTQ:
            return "reads"
    return "reads" if len(paths) == 2 else "genome"

def load_species_cutoffs_json(json_path: Path, species_key: str) -> dict:
    if not json_path.exists():
        raise FileNotFoundError(
            f"Missing species cutoffs JSON: {json_path}\n"
            "Run the container setup step that exports SPECIES_SEROVAR to JSON."
        )
    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if species_key not in data:
        raise KeyError(f"Species key '{species_key}' not found; available: {list(data.keys())}")
    return data[species_key]

def read_details(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if row[0].startswith('#'):
                continue
            if not row or len(row) < 2:
                continue
            sid = row[0].strip()
            files = [x.strip() for x in row[1].split(",") if x.strip()]
            if sid and files:
                yield sid, files

def ensure_paths():
    ALLELES_DIR.mkdir(parents=True, exist_ok=True)

def run_wrapper(strainid, intype, input_paths, o_arg, cutoffs,
                threads, memory, kraken_db, force, pathovar_key, refalleles, dry_run,
                min_largest_contig, max_contig_no, genome_min, genome_max, n50_min, hspident, locusnlimit, snpwindow, densitylim, refsize, blastident):
    i_arg = ",".join(str(p) for p in input_paths)
    cmd = [
        str(WRAPPER),
        "-i", str(i_arg),
        "--intype", intype,
        "-o", str(o_arg) + "/",
        "--strainid", strainid,
        "--species", cutoffs.get("species", "Xanthomonas citri"),
        "--threads", str(threads),
        "--memory", str(memory),
        "--min_largest_contig", str(cutoffs["min_largest_contig"]),
        "--max_contig_no", str(cutoffs["max_contig_no"]),
        "--genome_min", str(cutoffs["genome_min"]),
        "--genome_max", str(cutoffs["genome_max"]),
        "--n50_min", str(cutoffs["n50_min"]),
        "--hspident", str(cutoffs["hspident"]),
        "--locusnlimit", str(cutoffs["locusnlimit"]),
        "--snpwindow", str(cutoffs["snpwindow"]),
        "--densitylim", str(cutoffs["densitylim"]),
        "--refsize", str(cutoffs["refsize"]),
        "--blastident", str(cutoffs["blastident"]),
    ]
    if kraken_db:
        cmd += ["--kraken_db", str(kraken_db)]
    if pathovar_key:
        cmd += ["--pathovar", str(pathovar_key)]
    if refalleles:
        cmd += ["--refalleles", str(refalleles)]
    if min_largest_contig:
        cmd += ["--min_largest_contig", str(min_largest_contig)]
    else:
        cmd += ["--min_largest_contig", str(cutoffs["min_largest_contig"])]
    if max_contig_no:
        cmd += ["--max_contig_no", str(max_contig_no)]
    else:
        cmd += ["--max_contig_no", str(cutoffs["max_contig_no"])]
    if genome_min:
        cmd += ["--genome_min", str(genome_min)]
    else:
        cmd += ["--genome_min", str(cutoffs["genome_min"])]
    if genome_max:
        cmd += ["--genome_max", str(genome_max)]
    else:
        cmd += ["--genome_max", str(cutoffs["genome_max"])]
    if n50_min:
        cmd += ["--n50_min", str(n50_min)]
    else:
        cmd += ["--n50_min", str(cutoffs["n50_min"])]
    if hspident:
        cmd += ["--hspident", str(hspident)]
    else:
        cmd += ["--hspident", str(cutoffs["hspident"])]
    if locusnlimit:
        cmd += ["--locusnlimit", str(locusnlimit)]
    else:
        cmd += ["--locusnlimit", str(cutoffs["locusnlimit"])]
    if snpwindow:
        cmd += ["--snpwindow", str(snpwindow)]
    else:
        cmd += ["--snpwindow", str(cutoffs["snpwindow"])]
    if densitylim:
        cmd += ["--densitylim", str(densitylim)]
    else:
        cmd += ["--densitylim", str(cutoffs["densitylim"])]
    if refsize:
        cmd += ["--refsize", str(refsize)]
    else:
        cmd += ["--refsize", str(cutoffs["refsize"])]
    if blastident:
        cmd += ["--blastident", str(blastident)]
    else:
        cmd += ["--blastident", str(cutoffs["blastident"])]
    if force:
        cmd += ["--force"]

    print("[RUN]", " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=REPO_BASE).returncode

def main():
    ap = argparse.ArgumentParser(
        description="Batch executor for Reads2MGTAlleles",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--details_file", type=Path, help="Tab-delimied text file with Strain ID (first column) and Input data filename (second column; reads or assemblies). For paired reads please provide both filenames separated by a comma (e.g. reads_1.fastq.gz,reads_2.fastq.gz).", default=DETAILS_FILE)
    ap.add_argument("--source_dir", type=Path, required=True,
                    help="Directory containing the files referenced in details_file")
    ap.add_argument("--out_dir", type=Path, required=True,
                    help="Output directory for allele files")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--memory", type=int, default=8)
    ap.add_argument("--kraken_db", default=None)
    ap.add_argument("--pathovar_key", default=PATHOVAR_KEY, help=f"Text file translating MLST result to phylogenetic-associated pathovar.")
    ap.add_argument("--refalleles", default=REF_ALLELES, help=f"File path to MGT reference allele file.")
    ap.add_argument("--min_largest_contig",
                        help="Assembly quality filter: minimum allowable length of the largest contig in the assembly in bp",
                        type=int)
    ap.add_argument("--max_contig_no",
                        help="Assembly quality filter: maximum allowable number of contigs allowed for assembly",
                        type=int)
    ap.add_argument("--genome_min",
                        help="Assembly quality filter: minimum allowable total assembly length in bp",
                        type=int)
    ap.add_argument("--genome_max",
                        help="Assembly quality filter: maximum allowable total assembly length in bp",
                        type=int)
    ap.add_argument("--n50_min",
                        help="Assembly quality filter: minimum allowable n50 value in bp (default for salmonella)",
                        type=int)
    ap.add_argument("--hspident",
                        help="BLAST percentage identity needed for hsp to be returned",
                        type=float)
    ap.add_argument("--locusnlimit",
                        help="minimum proportion of the locus length that must be present (not masked with Ns)",
                        type=float)
    ap.add_argument("--snpwindow",
                        help="Size of sliding window to screen for overly dense SNPs",
                        type=int)
    ap.add_argument("--densitylim",
                        help="maximum number of SNPs allowed to be present in window before window is masked",
                        type=int)
    ap.add_argument("--refsize",
                        help="Approx size of genome for shovill input in megabases i.e. 5.0 or 2.9",type=float,
                        )
    ap.add_argument("--blastident",
                        help="BLAST percentage identity needed for hsp to be returned",
                        type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    ensure_paths()
    cutoffs = load_species_cutoffs_json(SPECIES_JSON, os.getenv("APPNAME"))

    failures = 0
    for strainid, file_list in read_details(args.details_file):
        print(f"\n=== Sample: {strainid} ===")
        try:
            src_files = []
            for f in file_list:
                p = Path(f)
                if not p.is_absolute():
                    p = args.source_dir / f
                if not p.exists():
                    raise FileNotFoundError(f"Input not found: {p}")
                src_files.append(p.resolve())

            intype = infer_intype(src_files)
            if intype == "reads" and len(src_files) != 2:
                raise ValueError(f"Reads input requires 2 files, got {len(src_files)}")

            rc = run_wrapper(strainid, intype, src_files, args.out_dir, cutoffs,
                             args.threads, args.memory, args.kraken_db,
                             args.force, args.pathovar_key, args.refalleles, args.dry_run, 
                             args.min_largest_contig, args.max_contig_no, args.genome_min, args.genome_max, args.n50_min, args.hspident, args.locusnlimit, args.snpwindow, args.densitylim, args.refsize, args.blastident)
            if rc != 0:
                raise RuntimeError(f"reads_to_alleles failed (exit {rc})")

        except Exception as e:
            failures += 1
            print(f"[ERROR] {strainid}: {e}")

    if failures:
        print(f"\nDone with {failures} failure(s).")
    else:
        print("\nDone. All samples processed successfully.")

if __name__ == "__main__":
    main()
