#!/usr/bin/env bash
# Usage: ./bench.sh [base-url] [model]
# Asks the same question 3 times through Ollama's native API and prints
# generation speed from its own counters (eval_count / eval_duration).
URL=${1:-http://localhost:8080}
MODEL=${2:-llama3.2:3b}
PROMPT="Explain what a Kubernetes Service does in about 150 words."
for i in 1 2 3; do
  curl -s "$URL/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"$PROMPT\",\"stream\":false,\"options\":{\"temperature\":0,\"num_predict\":200}}" |
    python3 -c 'import sys,json; r=json.load(sys.stdin); print("run %s: prompt %d tok @ %.1f tok/s, generated %d tok @ %.1f tok/s" % (sys.argv[1], r["prompt_eval_count"], r["prompt_eval_count"]/(r["prompt_eval_duration"]/1e9), r["eval_count"], r["eval_count"]/(r["eval_duration"]/1e9)))' $i
done
