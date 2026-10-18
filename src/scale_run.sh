#!/usr/bin/env bash
# 1,000-record scale run with Apertus 8B; times every stage into data/scale1000/timing.tsv
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/Scripts/python}
export LLM_NAME=apertus-v1-5-8b
mkdir -p data/scale1000
echo -e "stage\tseconds\texit" > data/scale1000/timing.tsv
for st in sample fetch classify audit enrich qc export; do
  t0=$(date +%s)
  $PY -X utf8 -u src/run.py "$st" --config src/config_scale1000.toml > "data/scale1000/log_$st.txt" 2>&1
  rc=$?
  echo -e "$st\t$(( $(date +%s) - t0 ))\t$rc" >> data/scale1000/timing.tsv
done
cat data/scale1000/timing.tsv
