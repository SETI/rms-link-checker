#!/usr/bin/env bash
#
# REPONAME - Run All Checks Script
#
# This script runs linting, type checking, tests, Sphinx build, and
# Markdown lint as separate checks. In parallel mode all requested
# checks run concurrently.
#
# Usage:
#   ./scripts/run-all-checks.sh [options]
#
# Options:
#   -p, --parallel   Run all requested checks in parallel (default)
#   -s, --sequential Run all requested checks sequentially
#   -c, --code       Run only code checks (ruff, mypy, pytest)
#   -d, --docs       Run only Sphinx build and Markdown lint (PyMarkdown)
#   -m, --markdown   Run only Markdown lint (PyMarkdown)
#   -h, --help       Show this help message
#
# Environment:
#   VENV or VENV_PATH  Path to virtualenv (default: $PROJECT_ROOT/venv)
#   CLEANUP_GRACE_PERIOD  Seconds to wait for graceful shutdown (default: 5)
#
# Checks (each run separately; -d runs both Sphinx and Markdown):
#   Code:    ruff check, ruff format --check, mypy, pytest
#   Sphinx:  make -C docs html SPHINXOPTS="-W"
#   Markdown: pymarkdown scan docs/ .cursor/ README.md CONTRIBUTING.md
#
# Exit codes:
#   0 - All requested checks passed
#   1 - One or more checks failed
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# Default options
PARALLEL=true
RUN_CODE=false
RUN_SPHINX=false
RUN_MARKDOWN=false
SCOPE_SPECIFIED=false

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="${VENV:-${VENV_PATH:-$PROJECT_ROOT/venv}}"

# Track failures and final exit code
FAILED_CHECKS=()
EXIT_CODE=0

# Temp directory for parallel output and status files
TEMP_DIR=$(mktemp -d)
# PIDs for background jobs (cleaned up on exit/signal)
code_pid=""
sphinx_pid=""
markdown_pid=""

# Grace period (seconds) before SIGKILL after SIGTERM
CLEANUP_GRACE_PERIOD=${CLEANUP_GRACE_PERIOD:-5}
if ! echo "$CLEANUP_GRACE_PERIOD" | grep -qE '^[0-9]+$'; then
    echo "Error: CLEANUP_GRACE_PERIOD must be a non-negative integer (got: $CLEANUP_GRACE_PERIOD)" >&2
    exit 1
fi

_wait_or_kill() {
    local pid=$1
    [ -z "$pid" ] && return 0
    kill -TERM "$pid" 2>/dev/null || true
    local waited=0
    while [ "$waited" -lt "$CLEANUP_GRACE_PERIOD" ]; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
    return 0
}

_cleanup() {
    _wait_or_kill "$code_pid"
    _wait_or_kill "$sphinx_pid"
    _wait_or_kill "$markdown_pid"
    code_pid=""
    sphinx_pid=""
    markdown_pid=""
    rm -rf "$TEMP_DIR"
}

# On signal: cleanup then exit with signal-specific code so we don't fall through
_cleanup_and_exit() {
    local sig_code=$1
    _cleanup
    exit "$sig_code"
}
trap '_cleanup_and_exit 130' SIGINT
trap '_cleanup_and_exit 143' SIGTERM
trap _cleanup EXIT

print_header() {
    echo -e "\n${BOLD}${BLUE}===================================================${RESET}"
    echo -e "${BOLD}${BLUE}  $1${RESET}"
    echo -e "${BOLD}${BLUE}===================================================${RESET}\n"
}

print_section() {
    echo -e "\n${BOLD}${YELLOW}>>> $1${RESET}\n"
}

print_success() {
    echo -e "${GREEN}✓${RESET} $1"
}

print_error() {
    echo -e "${RED}✗${RESET} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${RESET} $1"
}

show_usage() {
    sed -n '/^# Usage:/,/^# Exit codes:/p' "$0" | sed 's/^# //g' | sed 's/^#//g'
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -s|--sequential)
            PARALLEL=false
            shift
            ;;
        -c|--code)
            RUN_CODE=true
            SCOPE_SPECIFIED=true
            shift
            ;;
        -d|--docs)
            RUN_SPHINX=true
            RUN_MARKDOWN=true
            SCOPE_SPECIFIED=true
            shift
            ;;
        -m|--markdown)
            RUN_MARKDOWN=true
            SCOPE_SPECIFIED=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${RESET}" >&2
            show_usage
            exit 1
            ;;
    esac
done

# Default: run all checks
if [ "$SCOPE_SPECIFIED" = false ]; then
    RUN_CODE=true
    RUN_SPHINX=true
    RUN_MARKDOWN=true
fi

START_TIME=$(date +%s)

print_header "REPONAME - Running All Checks"

if [ "$PARALLEL" = true ]; then
    print_info "Running checks in PARALLEL mode"
else
    print_info "Running checks in SEQUENTIAL mode"
fi

# ---- Code checks (ruff, mypy, pytest) ----
run_code_checks() {
    local output_file="${1:-}"
    local status_file="${2:-}"

    if [ -n "$output_file" ]; then
        exec > "$output_file" 2>&1
    fi

    print_section "Code Checks"

    cd "$PROJECT_ROOT" || exit 1

    if [ ! -f "$VENV/bin/activate" ]; then
        print_error "Virtual environment not found at $VENV"
        [ -n "$status_file" ] && echo "Code - Virtual environment not found" >> "$status_file"
        return 1
    fi

    # shellcheck source=/dev/null
    source "$VENV/bin/activate"

    local failed=false
    local failed_checks=""

    if ! python -m ruff check src tests; then
        print_error "Ruff check failed"
        failed=true
        failed_checks="${failed_checks}Code - Ruff check"$'\n'
    else
        print_success "Ruff check passed"
    fi

    if ! python -m ruff format --check src tests; then
        print_error "Ruff format check failed"
        failed=true
        failed_checks="${failed_checks}Code - Ruff format"$'\n'
    else
        print_success "Ruff format check passed"
    fi

    if ! MYPYPATH=src python -m mypy src tests; then
        print_error "Mypy failed"
        failed=true
        failed_checks="${failed_checks}Code - Mypy"$'\n'
    else
        print_success "Mypy passed"
    fi

    if ! python -m pytest tests -q; then
        print_error "Pytest failed"
        failed=true
        failed_checks="${failed_checks}Code - Pytest"$'\n'
    else
        print_success "Pytest passed"
    fi

    deactivate 2>/dev/null || true

    if [ "$failed" = true ]; then
        [ -n "$status_file" ] && printf '%s' "$failed_checks" >> "$status_file"
        return 1
    fi
    return 0
}

# ---- Sphinx build only ----
run_sphinx_build() {
    local output_file="${1:-}"
    local status_file="${2:-}"

    if [ -n "$output_file" ]; then
        exec > "$output_file" 2>&1
    fi

    print_section "Sphinx Build"

    cd "$PROJECT_ROOT" || exit 1

    if [ ! -f "$VENV/bin/activate" ]; then
        print_error "Virtual environment not found at $VENV"
        [ -n "$status_file" ] && echo "Sphinx - Virtual environment not found" >> "$status_file"
        return 1
    fi

    # shellcheck source=/dev/null
    source "$VENV/bin/activate"

    print_info "Building documentation (warnings treated as errors)..."
    if (cd docs && make clean && make html SPHINXOPTS="-W"); then
        print_success "Sphinx build passed"
        deactivate 2>/dev/null || true
        return 0
    else
        print_error "Sphinx build failed"
        [ -n "$status_file" ] && echo "Sphinx - Sphinx build" >> "$status_file"
        deactivate 2>/dev/null || true
        return 1
    fi
}

# ---- Markdown lint only (PyMarkdown) ----
run_markdown_checks() {
    local output_file="${1:-}"
    local status_file="${2:-}"

    if [ -n "$output_file" ]; then
        exec > "$output_file" 2>&1
    fi

    print_section "Markdown Lint (PyMarkdown)"

    cd "$PROJECT_ROOT" || exit 1

    if [ ! -f "$VENV/bin/activate" ]; then
        print_error "Virtual environment not found at $VENV"
        [ -n "$status_file" ] && echo "Markdown - Virtual environment not found" >> "$status_file"
        return 1
    fi

    # shellcheck source=/dev/null
    source "$VENV/bin/activate"

    print_info "Running PyMarkdown scan (docs/, .cursor/, root *.md)..."
    if python -m pymarkdown scan docs/ .cursor/ README.md CONTRIBUTING.md; then
        print_success "PyMarkdown scan passed"
        deactivate 2>/dev/null || true
        return 0
    else
        print_error "PyMarkdown scan failed"
        [ -n "$status_file" ] && echo "Markdown - PyMarkdown scan" >> "$status_file"
        deactivate 2>/dev/null || true
        return 1
    fi
}

# ---- Collect status from a status file into FAILED_CHECKS ----
_collect_status() {
    local status_file=$1
    if [ -f "$status_file" ]; then
        while IFS= read -r line; do
            [ -n "$line" ] && FAILED_CHECKS+=("$line")
        done < "$status_file"
    fi
}

# ---- Run requested checks ----
if [ "$PARALLEL" = true ]; then
    # Start each requested check in background and record PIDs
    print_info "Running requested checks in parallel, please wait..."

    if [ "$RUN_CODE" = true ]; then
        code_output="$TEMP_DIR/code.log"
        code_status="$TEMP_DIR/code.status"
        run_code_checks "$code_output" "$code_status" &
        code_pid=$!
    fi

    if [ "$RUN_SPHINX" = true ]; then
        sphinx_output="$TEMP_DIR/sphinx.log"
        sphinx_status="$TEMP_DIR/sphinx.status"
        run_sphinx_build "$sphinx_output" "$sphinx_status" &
        sphinx_pid=$!
    fi

    if [ "$RUN_MARKDOWN" = true ]; then
        markdown_output="$TEMP_DIR/markdown.log"
        markdown_status="$TEMP_DIR/markdown.status"
        run_markdown_checks "$markdown_output" "$markdown_status" &
        markdown_pid=$!
    fi

    # Wait for each job and capture exit code; any failure sets EXIT_CODE=1
    if [ -n "$code_pid" ]; then
        if ! wait "$code_pid"; then
            EXIT_CODE=1
        fi
        code_pid=""
        _collect_status "${TEMP_DIR}/code.status"
    fi

    if [ -n "$sphinx_pid" ]; then
        if ! wait "$sphinx_pid"; then
            EXIT_CODE=1
        fi
        sphinx_pid=""
        _collect_status "${TEMP_DIR}/sphinx.status"
    fi

    if [ -n "$markdown_pid" ]; then
        if ! wait "$markdown_pid"; then
            EXIT_CODE=1
        fi
        markdown_pid=""
        _collect_status "${TEMP_DIR}/markdown.status"
    fi

    # Print all output in a fixed order
    echo ""
    [ -f "${TEMP_DIR}/code.log" ] && cat "${TEMP_DIR}/code.log"
    [ -f "${TEMP_DIR}/sphinx.log" ] && cat "${TEMP_DIR}/sphinx.log"
    [ -f "${TEMP_DIR}/markdown.log" ] && cat "${TEMP_DIR}/markdown.log"
else
    # Sequential
    if [ "$RUN_CODE" = true ]; then
        if ! run_code_checks; then
            EXIT_CODE=1
        fi
    fi

    if [ "$RUN_SPHINX" = true ]; then
        if ! run_sphinx_build; then
            EXIT_CODE=1
        fi
    fi

    if [ "$RUN_MARKDOWN" = true ]; then
        if ! run_markdown_checks; then
            EXIT_CODE=1
        fi
    fi
fi

# ---- Summary ----
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
ELAPSED_SECONDS=$((ELAPSED % 60))

print_header "Summary"

if [ "$EXIT_CODE" -eq 0 ]; then
    print_success "All checks passed!"
    echo -e "${GREEN}${BOLD}✓ SUCCESS${RESET} - All checks completed successfully"
else
    print_error "Some checks failed:"
    if [ ${#FAILED_CHECKS[@]} -eq 0 ]; then
        echo -e "  ${RED}✗${RESET} One or more checks failed (see output above)"
    else
        for check in "${FAILED_CHECKS[@]}"; do
            echo -e "  ${RED}✗${RESET} $check"
        done
    fi
    echo -e "${RED}${BOLD}✗ FAILURE${RESET} - One or more check(s) failed"
fi

echo ""
print_info "Total time: ${MINUTES}m ${ELAPSED_SECONDS}s"
echo ""

exit "$EXIT_CODE"
