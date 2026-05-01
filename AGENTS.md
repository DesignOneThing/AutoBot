# Project Context

## Runtime

- The bot is configured to auto-start on this Mac through `launchd`.
- LaunchAgent path:
  `/Users/lenapoll/Library/LaunchAgents/com.designonething.avtonetbot.plist`
- The auto-started runtime copy is:
  `/Users/lenapoll/AutoBotRuntime`
- The development workspace is:
  `/Users/lenapoll/Documents/Code/AutoBot`
- Do not manually start `python -m avtonet_bot` while the LaunchAgent is running, because Telegram polling allows only one active `getUpdates` consumer per bot token. Running two copies causes `409 Conflict`.

## Editing Rules

- Make source changes in `/Users/lenapoll/Documents/Code/AutoBot`.
- After code/config changes that should affect the running local bot, sync the workspace into `/Users/lenapoll/AutoBotRuntime` and restart the LaunchAgent.
- Preserve `.env`; it contains local secrets and is intentionally gitignored.
- Do not print or commit Telegram tokens, proxy credentials, SQLite database files, WAL/SHM files, or logs.
- SQLite runtime files are local state and should not be committed.
- Render may be stopped while the local bot is active. If Render and local launchd use the same token at the same time, Telegram will return `409 Conflict`.

## Useful Commands

Stop local auto-started bot:

```bash
launchctl bootout gui/$(id -u) /Users/lenapoll/Library/LaunchAgents/com.designonething.avtonetbot.plist
```

Start local auto-started bot:

```bash
launchctl bootstrap gui/$(id -u) /Users/lenapoll/Library/LaunchAgents/com.designonething.avtonetbot.plist
```

Check status:

```bash
launchctl print gui/$(id -u)/com.designonething.avtonetbot
```

Watch logs:

```bash
tail -f /Users/lenapoll/AutoBotRuntime/logs/launchd.err.log
```

Sync workspace to runtime copy:

```bash
rsync -a --delete --exclude .git --exclude .pytest_cache --exclude logs /Users/lenapoll/Documents/Code/AutoBot/ /Users/lenapoll/AutoBotRuntime/
```

Then restart the LaunchAgent.
