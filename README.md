# Legacy WireGuard / AmneziaWG Bot

> **Legacy VPN automation project. Not part of the active portfolio showcase.**

This repository contains an older Telegram-based VPN management project with WireGuard/AmneziaWG setup, user configuration generation, subscription logic and operational scripts.

## Security cleanup

A tracked runtime SQLite database (`wg_bot.db`) was removed from the current branch. Runtime databases and generated client configurations are already excluded by `.gitignore` and must stay outside source control.

The database historically contained user/subscription/configuration state, so historical Git objects should be treated as sensitive until repository history is fully sanitized.

## Runtime data policy

The following belong on the server or in encrypted backups, never in Git:

```text
.env
*.db
wg_configs/
private keys
preshared keys
client configuration files
runtime backups
```

## Portfolio note

This is retained as a legacy infrastructure project. The current portfolio focus is on the newer production FastAPI/PostgreSQL/Redis/AI systems.
