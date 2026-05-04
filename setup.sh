#!/bin/sh
# setup.sh — P2P Whitelabel Bot Setup Wizard
# Usage: sh setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_ok()  { printf "${GREEN}✓ %s${NC}\n" "$1"; }
print_warn(){ printf "${YELLOW}⚠ %s${NC}\n" "$1"; }
print_err() { printf "${RED}✗ %s${NC}\n" "$1"; exit 1; }

# Check prerequisites
command -v docker >/dev/null 2>&1 || print_err "Docker not found. Install from https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || print_err "docker compose plugin not found."
command -v python3 >/dev/null 2>&1 || print_err "Python 3 not found."
print_ok "Prerequisites verified"

# Collect inputs
printf "\n${YELLOW}=== P2P Whitelabel Bot Setup ===${NC}\n\n"

if [ -f .env ]; then
    print_warn ".env already exists. Running setup will overwrite it."
    printf "Continue? (y/n): "
    read -r CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        print_err "Setup aborted by user."
    fi
fi

printf "Enter your BOT_TOKEN from @BotFather: "
read -r BOT_TOKEN
[ -z "$BOT_TOKEN" ] && print_err "BOT_TOKEN cannot be empty."

printf "Enter your CRYPTOPAY_TOKEN from @CryptoBot: "
read -r CRYPTOPAY_TOKEN
[ -z "$CRYPTOPAY_TOKEN" ] && print_err "CRYPTOPAY_TOKEN cannot be empty."

printf "Enter ADMIN_IDS (comma-separated Telegram user IDs): "
read -r ADMIN_IDS
[ -z "$ADMIN_IDS" ] && print_err "ADMIN_IDS cannot be empty."

printf "Enter GEMINI_API_KEY (optional, press Enter to skip): "
read -r GEMINI_API_KEY

# Generate secrets
AES_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
CALLBACK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
print_ok "Secrets generated"

# Create .env from example
cp .env.example .env

# Replace values in .env
# We use a temporary file for compatibility with different sed versions
sed "s|your_telegram_bot_token_here|$BOT_TOKEN|g" .env > .env.tmp && mv .env.tmp .env
sed "s|your_cryptopay_token_here|$CRYPTOPAY_TOKEN|g" .env > .env.tmp && mv .env.tmp .env
sed "s|your_cryptopay_callback_secret_here|$CALLBACK_SECRET|g" .env > .env.tmp && mv .env.tmp .env
sed "s|your_64_char_hex_aes_key_here|$AES_KEY|g" .env > .env.tmp && mv .env.tmp .env
sed "s|123456789,987654321|$ADMIN_IDS|g" .env > .env.tmp && mv .env.tmp .env
sed "s|your_gemini_api_key_here|$GEMINI_API_KEY|g" .env > .env.tmp && mv .env.tmp .env

# Update POSTGRES_URI with random password
# Note: In docker-compose, the host is 'postgres'
sed "s|postgresql+asyncpg://p2pbot:password@localhost:5432/p2pbot|postgresql+asyncpg://p2pbot:$POSTGRES_PASSWORD@postgres:5432/p2pbot|g" .env > .env.tmp && mv .env.tmp .env

# Also add the raw password for the postgres container env if needed
# (Assuming docker-compose.yml uses POSTGRES_PASSWORD env var)
if ! grep -q "POSTGRES_PASSWORD=" .env; then
    printf "\n# Postgres container password\nPOSTGRES_PASSWORD=%s\n" "$POSTGRES_PASSWORD" >> .env
fi

print_ok ".env file configured"

# Copy branding config if not exists
if [ ! -f branding.yaml ]; then
    if [ -f branding.yaml.example ]; then
        cp branding.yaml.example branding.yaml
        print_ok "branding.yaml created from example"
    else
        print_warn "branding.yaml.example not found. Please create branding.yaml manually."
    fi
else
    print_warn "branding.yaml already exists — skipping"
fi

# Make itself executable (not really needed for .sh but good practice)
chmod +x setup.sh

printf "\n${GREEN}=== Setup Complete ===${NC}\n"
printf "Next steps:\n"
printf "  1. (Optional) Edit ${YELLOW}branding.yaml${NC} to customize bot name and fees.\n"
printf "  2. Run: ${YELLOW}docker compose up -d --build${NC}\n"
printf "  3. Check logs: ${YELLOW}docker compose logs -f bot${NC}\n\n"
printf "Your unique AES_KEY is stored in .env. ${RED}NEVER SHARE IT.${NC}\n"
