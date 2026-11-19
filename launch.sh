#!/usr/bin/env bash
# Start Athena v2: Ollama with the shared model, then the Streamlit app in your browser.
#
#   ./launch.sh          set up anything missing, then open the app
#   ./launch.sh stop     stop the app
set -euo pipefail
cd "$(dirname "$0")"

# Settings from .env; variables already set in the shell win.
env_value() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//' || true; }
setting() { local v="${!1:-}"; [ -n "$v" ] && printf '%s' "$v" || { v=$(env_value "$1"); printf '%s' "${v:-$2}"; }; }

MODEL=$(setting ATHENA_MODEL dsv4-heretic)
GGUF=hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-i1-GGUF:i1-Q6_K
IMAGE_MODEL=$(setting ATHENA_IMAGE_MODEL Runpod/FLUX.2-klein-4B-mflux-4bit)
OLLAMA=$(setting OLLAMA_URL http://127.0.0.1:11434)
PORT=$(setting ATHENA_PORT 8501)
URL=http://localhost:$PORT
LOG=data/app.log

step() { printf '\033[36m▸\033[0m %s\n' "$*"; }
good() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }
ollama_up() { curl -sf -m 3 "$OLLAMA/api/version" >/dev/null 2>&1; }
app_up() { curl -sf -m 3 "$URL/_stcore/health" >/dev/null 2>&1; }
app_pid() { lsof -t -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true; }

if [ "${1:-}" = stop ]; then
  pid=$(app_pid)
  if [ -z "$pid" ]; then good "Athena wasn't running"; exit 0; fi
  kill "$pid"
  # Wait until the port is actually free, so a start right after this works.
  for _ in $(seq 1 20); do [ -z "$(app_pid)" ] && break; sleep 0.5; done
  [ -z "$(app_pid)" ] || kill -9 "$pid" 2>/dev/null || true
  good "Athena stopped"
  exit 0
fi

if app_up; then
  good "Athena is already running"
  open "$URL"
  exit 0
fi
[ -z "$(app_pid)" ] || die "port $PORT is used by another program (set ATHENA_PORT to use a different one)"

step "Python environment"
command -v uv >/dev/null || die "uv is required: brew install uv"
[ -d .venv ] || uv venv -q --python 3.12 .venv
uv pip install -q --python .venv/bin/python -r requirements.txt
good ".venv ready"

step "Ollama"
command -v ollama >/dev/null || die "Ollama is required: brew install ollama"
if ! ollama_up; then
  open -ga Ollama 2>/dev/null || (mkdir -p data && nohup ollama serve >data/ollama.log 2>&1 &)
  for _ in $(seq 1 30); do ollama_up && break; sleep 1; done
  ollama_up || die "Ollama didn't start"
fi
installed() { ollama list | awk 'NR > 1 { print $1 }' | grep -qx "$1"; }
if [ "$MODEL" = dsv4-heretic ]; then
  if ! installed "dsv4-heretic:latest"; then
    installed "$GGUF" || { echo "  downloading the model (~7.6 GB)..."; ollama pull "$GGUF"; }
    ollama create dsv4-heretic -f models/dsv4-heretic.Modelfile >/dev/null
  fi
else
  tagged=$MODEL; case $MODEL in *:*) ;; *) tagged="$MODEL:latest" ;; esac
  installed "$tagged" || { echo "  downloading $MODEL..."; ollama pull "$MODEL"; }
fi
good "$MODEL installed"

step "Image model"
if [ ! -d "$HOME/.cache/huggingface/hub/models--${IMAGE_MODEL//\//--}" ]; then
  echo "  downloading FLUX.2 [klein] 4B, 4-bit (~4.6 GB)..."
  .venv/bin/hf download "$IMAGE_MODEL" >/dev/null
fi
good "$IMAGE_MODEL ready"

step "Athena"
mkdir -p data
# Headless: no first-run prompts in the terminal; the browser is opened below once the app answers.
# Bound to localhost only: the app can reach the uncensored model and reveal files in Finder.
nohup .venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port "$PORT" \
  --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false \
  </dev/null >"$LOG" 2>&1 &
for _ in $(seq 1 60); do app_up && break; sleep 0.5; done
app_up || { tail -20 "$LOG"; die "Athena didn't start (log: $LOG)"; }
good "$URL"
open "$URL"
echo "Stop it with: ./launch.sh stop"
