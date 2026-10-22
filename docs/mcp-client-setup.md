# MCP Client Setup

`mcp-tools-sql` with no subcommand (or `mcp-tools-sql server`) runs the MCP
server over stdio. Any MCP client that launches stdio servers can use it.

Before wiring it into a client, get a clean `mcp-tools-sql verify` from a
terminal — clients usually hide a server's startup errors.

## Rules that apply to every client

- **Pass an absolute `--config`.** Config discovery uses the working directory,
  and the client decides what that is. Without `--config`, the server only
  works if the client starts it in the project directory. A relative sqlite
  `path` in the database config also resolves from the client's working
  directory, so use an absolute path there too.
- **Pass passwords through the environment.** Reference them in the database
  config as `password = "${MSSQL_PASSWORD}"` and set the variable in the
  client's `env` block (or the environment the client inherits).
- **Use the full path to the executable** if `mcp-tools-sql` is installed in a
  virtualenv that isn't on the client's `PATH`, e.g.
  `C:/projects/demo/.venv/Scripts/mcp-tools-sql.exe`.
- **Logs.** Each launch writes `~/.mcp-tools-sql/logs/mcp_tools_sql_<timestamp>.log`.
  When the server doesn't show up in the client, read the newest file there.

## Claude Code (`.mcp.json` in the project root)

```json
{
  "mcpServers": {
    "sql": {
      "type": "stdio",
      "command": "mcp-tools-sql",
      "args": ["--config", "C:/projects/demo/mcp-tools-sql.toml"],
      "env": {
        "MSSQL_PASSWORD": "${MSSQL_PASSWORD}"
      }
    }
  }
}
```

Claude Code expands `${VAR}` in `.mcp.json` from its own environment, so the
password never lands in the file.

## Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "sql": {
      "command": "C:/projects/demo/.venv/Scripts/mcp-tools-sql.exe",
      "args": [
        "--config", "C:/projects/demo/mcp-tools-sql.toml",
        "--database-config", "C:/Users/me/.mcp-tools-sql/config.toml"
      ]
    }
  }
}
```

## Useful server flags

| Flag | Use |
|------|-----|
| `--config PATH` | Project query config (absolute path recommended). |
| `--database-config PATH` | Non-default database config, e.g. per-environment files. |
| `--log-level DEBUG` | More detail in the log file. |
| `--log-file PATH` | Fixed log file instead of one per launch. |

See [configuration.md](configuration.md) for the config files and
[cli.md](cli.md) for every flag.
