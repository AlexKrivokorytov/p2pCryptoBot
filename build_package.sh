#!/usr/bin/env bash
# build_package.sh — Build the final white-label delivery package.
#
# USAGE (run on YOUR machine as the seller):
#   bash build_package.sh
#
# OUTPUT:
#   p2pbot-whitelabel-v1.0.zip  ← ready to send to buyers
#
# REQUIREMENTS:
#   - Docker with buildx support
#   - zip
#   - Python 3.12 with Cython installed (pip install cython)
#   - SELLER_SECRET environment variable set
#
# HOW IT WORKS:
#   1. Verifies SELLER_SECRET is set (required to bake license check into build).
#   2. Builds the Docker image from the current source (multi-stage, non-root).
#   3. Exports the Docker image as a .tar file (buyers load it, never see source).
#   4. Packages only buyer-facing files into the final ZIP:
#      - p2pbot-image.tar       ← sealed Docker image (no source code inside)
#      - docker-compose.yml     ← one-command deployment
#      - .env.example           ← documented environment variables
#      - branding.yaml.example  ← white-label customization template
#      - setup.sh               ← guided setup wizard
#      - README.md              ← quick start guide with security badges
#      - PRICING.md             ← tier descriptions and EULA
#   5. Strips all internal files (WHITELABEL_PLAN.md, tests, .git, .env, etc.)

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
VERSION="1.0"
IMAGE_NAME="p2pbot-whitelabel"
IMAGE_TAG="v${VERSION}"
ARCHIVE_NAME="p2pbot-whitelabel-v${VERSION}.zip"
TEMP_DIR="$(mktemp -d)"

echo "======================================================================"
echo "  p2pCryptoBot — Build Delivery Package v${VERSION}"
echo "======================================================================"

# ── Step 1: Pre-flight checks ─────────────────────────────────────────────────
echo ""
echo "[1/5] Running pre-flight checks..."

if [[ -z "${SELLER_SECRET:-}" ]]; then
    echo "ERROR: SELLER_SECRET environment variable is not set."
    echo "       This is your private key used to generate license keys for buyers."
    echo "       Generate it once with:"
    echo "         python -c \"import secrets; print(secrets.token_hex(32))\""
    echo "       Then set it: export SELLER_SECRET=<your_secret>"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed or not in PATH."
    exit 1
fi

if ! command -v zip &>/dev/null; then
    echo "ERROR: 'zip' is not installed. Install it with: apt-get install zip"
    exit 1
fi

echo "  ✅ All pre-flight checks passed."

# ── Step 2: Run final test suite to confirm quality ───────────────────────────
echo ""
echo "[2/5] Running final test suite..."

if python -m pytest --tb=short -q 2>&1 | tail -5; then
    echo "  ✅ All tests passed."
else
    echo "ERROR: Tests failed. Fix all failures before building the delivery package."
    exit 1
fi

# ── Step 3: Build the sealed Docker image ────────────────────────────────────
echo ""
echo "[3/5] Building sealed Docker image (${IMAGE_NAME}:${IMAGE_TAG})..."
echo "      This bakes compiled code into the image. No Python source visible."

docker build \
    --build-arg SELLER_SECRET="${SELLER_SECRET}" \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    --file Dockerfile \
    . 

echo "  ✅ Docker image built successfully."

# ── Step 4: Export the image to a .tar archive ───────────────────────────────
echo ""
echo "[4/5] Exporting Docker image to p2pbot-image.tar..."

docker save --output "${TEMP_DIR}/p2pbot-image.tar" "${IMAGE_NAME}:${IMAGE_TAG}"

echo "  ✅ Image exported: $(du -sh "${TEMP_DIR}/p2pbot-image.tar" | cut -f1)"

# ── Step 5: Assemble the delivery package ─────────────────────────────────────
echo ""
echo "[5/5] Assembling delivery package..."

# Copy only buyer-facing files into temp dir
cp docker-compose.yml    "${TEMP_DIR}/docker-compose.yml"
cp .env.example          "${TEMP_DIR}/.env.example"
cp branding.yaml.example "${TEMP_DIR}/branding.yaml.example"
cp setup.sh              "${TEMP_DIR}/setup.sh"
cp README.md             "${TEMP_DIR}/README.md"
cp PRICING.md            "${TEMP_DIR}/PRICING.md"

# Create the final ZIP from the temp directory
(cd "${TEMP_DIR}" && zip -r9 - .) > "${ARCHIVE_NAME}"

# Cleanup
rm -rf "${TEMP_DIR}"

echo ""
echo "======================================================================"
echo "  ✅ Delivery package ready: ${ARCHIVE_NAME}"
echo "  📦 Size: $(du -sh "${ARCHIVE_NAME}" | cut -f1)"
echo ""
echo "  Package contents (what the buyer receives):"
echo "    ├── p2pbot-image.tar       ← Sealed Docker image (no source code)"
echo "    ├── docker-compose.yml     ← One-command deployment"
echo "    ├── .env.example           ← All env variables documented"
echo "    ├── branding.yaml.example  ← White-label customization template"
echo "    ├── setup.sh               ← Guided setup wizard"
echo "    ├── README.md              ← Quick start guide"
echo "    └── PRICING.md             ← Tier descriptions and EULA"
echo ""
echo "  NEXT STEP: Generate a license key for your buyer:"
echo "    python -c \""
echo "    from utils.license_guard import generate_license_key"
echo "    print(generate_license_key('BUYER_BOT_TOKEN_HERE'))"
echo "    \""
echo "======================================================================"
