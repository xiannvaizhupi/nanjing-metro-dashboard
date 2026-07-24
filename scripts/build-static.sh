#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dist_dir="$root_dir/dist"

rm -rf "$dist_dir"
mkdir -p "$dist_dir/css" "$dist_dir/js" "$dist_dir/data"

cp "$root_dir/index.html" "$dist_dir/"
cp "$root_dir/lines.html" "$dist_dir/"
cp "$root_dir/history.html" "$dist_dir/"
cp "$root_dir/Nanjing_Metro_Logo.svg.png" "$dist_dir/"

cp "$root_dir/css/apple-style.css" "$dist_dir/css/"
cp "$root_dir/css/logo.css" "$dist_dir/css/"
cp "$root_dir/css/style.css" "$dist_dir/css/"

cp "$root_dir/js/main.js" "$dist_dir/js/"

cp "$root_dir/data/metro_data.json" "$dist_dir/data/"
cp "$root_dir/data/weather.json" "$dist_dir/data/"
cp "$root_dir/data/prediction_log.json" "$dist_dir/data/"
cp "$root_dir/data/ml_predictions.json" "$dist_dir/data/"

printf 'Static site built at %s\n' "$dist_dir"
