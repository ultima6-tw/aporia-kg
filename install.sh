#!/usr/bin/env bash
set -e

# ─── colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}[Aporia KG]${RESET} $*"; }
success() { echo -e "${GREEN}✔${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "${RED}✘${RESET}  $*"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        Aporia KG  Installer          ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ─── Python check ──────────────────────────────────────────────────────────
info "Checking Python version..."
PY=""
for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info[:2])")
        # require >= 3.11
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PY="$cmd"
            break
        fi
    fi
done
[ -z "$PY" ] && error "Python 3.11+ is required. Install it from https://python.org and try again."
success "Found $($PY --version)"

# ─── Virtual env ───────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment (.venv)..."
    "$PY" -m venv .venv
    success "Virtual environment created"
else
    success "Virtual environment already exists"
fi

source .venv/bin/activate

# ─── Dependencies ──────────────────────────────────────────────────────────
info "Installing dependencies (this may take a minute)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Dependencies installed"

# ─── LLM backend ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}LLM Backend Setup${RESET}"
echo "  [1] Gemini  – requires a free API key from Google AI Studio"
echo "  [2] Ollama  – fully local, no API key needed (Ollama must be installed)"
echo ""
while true; do
    read -rp "Choose backend [1/2]: " BACKEND_CHOICE
    case "$BACKEND_CHOICE" in
        1) LLM_BACKEND="gemini"; break ;;
        2) LLM_BACKEND="ollama"; break ;;
        *) warn "Please enter 1 or 2" ;;
    esac
done

GEMINI_API_KEY=""
if [ "$LLM_BACKEND" = "gemini" ]; then
    echo ""
    echo -e "Get a free key at: ${CYAN}https://aistudio.google.com/${RESET}"
    while true; do
        read -rp "Paste your Gemini API key: " GEMINI_API_KEY
        if [ -n "$GEMINI_API_KEY" ]; then
            break
        fi
        warn "API key cannot be empty"
    done
else
    # check Ollama is running
    if ! command -v ollama &>/dev/null; then
        warn "Ollama not found. Install it from https://ollama.ai and run: ollama pull gemma3 && ollama pull nomic-embed-text"
    else
        success "Ollama found"
        info "Make sure you have pulled a model, e.g.:"
        echo "    ollama pull gemma3"
        echo "    ollama pull nomic-embed-text"
    fi
fi

# ─── Write .env ────────────────────────────────────────────────────────────
if [ -f ".env" ]; then
    warn ".env already exists — creating .env.backup before overwriting"
    cp .env .env.backup
fi

cat > .env <<EOF
# LLM Backend: "gemini" or "ollama"
LLM_BACKEND=${LLM_BACKEND}

# Gemini API key (required if LLM_BACKEND=gemini)
GEMINI_API_KEY=${GEMINI_API_KEY}

# PostgreSQL connection URL (optional, leave blank to use SQLite)
# DATABASE_URL=postgresql://user:password@localhost:5432/ragraphe
EOF
success ".env written"

# ─── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Installation complete!${RESET}"
echo ""
echo "To start Aporia KG:"
echo -e "  ${CYAN}source .venv/bin/activate${RESET}"
echo -e "  ${CYAN}uvicorn ragraphe.api.main:app --port 7860${RESET}"
echo ""

# ask to start now
read -rp "Start Aporia KG now? [Y/n]: " START_NOW
START_NOW="${START_NOW:-Y}"
if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
    info "Starting server at http://localhost:7860 ..."
    # open browser (macOS / Linux)
    (sleep 2 && (open "http://localhost:7860" 2>/dev/null || xdg-open "http://localhost:7860" 2>/dev/null)) &
    uvicorn ragraphe.api.main:app --port 7860
fi
