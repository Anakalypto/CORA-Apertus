#!/usr/bin/env bash
# 10,000-record mixed batch (tiers x types x eras, src/cora/mixed.py); times every stage into data/batch10k/timing.tsv
# Stages are incremental: a re-run skips what is done. Start from a later stage with: src/batch_run.sh audit
set -u
cd "$(dirname "$0")/.."
PY=${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo .venv/Scripts/python )}
CFG=src/config_batch10k.toml
OUT=data/batch10k
mkdir -p $OUT
[ -f $OUT/enrich_cache.json ] || cp data/enrich_cache.json $OUT/   # reuse the geocoder / Wikidata cache of the demo
[ -f $OUT/timing.tsv ] || echo -e "stage\tseconds\texit" > $OUT/timing.tsv
STAGES="mixed_sample classify audit level repair enrich qc export"
[ $# -gt 0 ] && STAGES=$(echo "$STAGES" | sed "s/.*\b$1\b/$1/")
for st in $STAGES; do
  [ "$st" = mixed_sample ] && [ -f $OUT/records_raw.json ] && continue
  t0=$(date +%s)
  $PY -X utf8 -u src/run.py "$st" --config $CFG > "$OUT/log_$st.txt" 2>&1
  rc=$?
  echo -e "$st\t$(( $(date +%s) - t0 ))\t$rc" >> $OUT/timing.tsv
  [ $rc -ne 0 ] && [ "$st" != qc ] && { echo "stage $st failed (exit $rc), see $OUT/log_$st.txt"; exit $rc; }
done
cat $OUT/timing.tsv
