#!/bin/bash
# Daily backup of wg-bot: DB, client configs, server config
# Sends to admin chats via Telegram API

set -euo pipefail

BOT_DIR="/root/wg-bot"
BACKUP_DIR="/root/backups/wg-bot"
TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/wg-bot-backup-$TIMESTAMP.tar.gz"

# Extract token from .env
TOKEN=$(grep -E '^BOT_TOKEN=' "$BOT_DIR/.env" | head -1 | cut -d= -f2- | tr -d \")
ADMINS=$(grep -E '^ADMIN_IDS=' "$BOT_DIR/.env" | head -1 | cut -d= -f2- | tr -d \")

mkdir -p "$BACKUP_DIR"

# Create archive with all critical data
tar czf "$BACKUP_FILE" \
    -C "$BOT_DIR" \
    wg_bot.db \
    wg_configs/ \
    /etc/amnezia/amneziawg/wg0.conf

# Count client configs
CONFIG_COUNT=$(ls "$BOT_DIR/wg_configs/"*.conf 2>/dev/null | wc -l)

# Send to each admin
IFS=',' read -ra ADMIN_LIST <<< "$ADMINS"
for ADMIN_ID in "${ADMIN_LIST[@]}"; do
    ADMIN_ID=$(echo "$ADMIN_ID" | xargs)
    curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendDocument" \
        -F chat_id="$ADMIN_ID" \
        -F document=@"$BACKUP_FILE" \
        -F caption="📦 WG-Bot daily backup ($TIMESTAMP)
• Database: wg_bot.db
• Client configs: $CONFIG_COUNT files
• Server config: wg0.conf
• All keys included" > /dev/null
done

# Keep last 7 backups, log
find "$BACKUP_DIR" -name 'wg-bot-backup-*.tar.gz' -mtime +7 -delete
echo "$(date): Backup sent ($CONFIG_COUNT configs)" >> "$BACKUP_DIR/backup.log"
