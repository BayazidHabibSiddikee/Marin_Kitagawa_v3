#!/bin/bash
# Activate Marin HS-02 virtual environment
# Usage: source activate.sh

VENV_PATH="$HOME/.venv/langchain-fix"

if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "✓ Marin venv activated ($VENV_PATH)"
else
    echo "✗ Venv not found at $VENV_PATH"
    echo "  Create one: python3 -m venv $VENV_PATH && source $VENV_PATH/bin/activate"
    return 1 2>/dev/null || exit 1
fi

# Ensure we're in the project root
cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null
echo "✓ Project root: $(pwd)"
