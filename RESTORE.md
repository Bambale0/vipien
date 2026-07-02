# WG-Bot Restore Guide
# If the server dies, here's how to restore all configs

## Files to restore from backup .tar.gz:
1. wg_bot.db — database (users, subs, keys, configs)
2. wg_configs/ — per-user .conf files + QR pngs
3. wg0.conf — server WireGuard config

## Quick restore on new server:
1. Install AmneziaWG server
2. Copy wg0.conf → /etc/amnezia/amneziawg/wg0.conf
3. Copy wg_bot.db → /root/wg-bot/wg_bot.db
4. Copy wg_configs/ → /root/wg-bot/wg_configs/
5. Restart wg service + wg-bot

## If wg-bot is dead but users need access:
All client configs are in wg_configs/ as .conf files.
Users can import them directly into any WireGuard client.
Each file is named user_{telegram_id}_{number}.conf

## Keys location:
- Server private key: in /etc/amnezia/amneziawg/wg0.conf
- Client keys: in wg_configs/*.conf and wg_bot.db
- QR codes: wg_configs/*.png (ready to scan)
