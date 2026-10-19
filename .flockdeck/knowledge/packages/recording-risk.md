---
type: Module
title: Risky action rules
description: Rule-based heuristics that flag risky tool calls such as force pushes, rm -rf, destructive SQL and secret files.
resource: src/lens/recording/risk.py
tags: [recording, risk, heuristics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/risk.py]
---
The module says it is heuristics, not a security boundary. `find_risky_actions(events)` examines each `tool_call` and returns [RiskyAction](../tables/risky-action.md) entries, at most one per rule per call (the most severe hit).

Bash commands are split on `&&`, `||`, `;`, `&`, `|` and newlines, tokenised with shlex, and `sudo`, `time`, `env`, `command` wrappers are peeled off.

| Rule | Trigger | Severity |
|---|---|---|
| `rm_rf` | recursive `rm`; targets such as `/`, `~`, `.`, `..`, `$HOME` or a bare glob | high; else medium with force, low without |
| `git_force_push` | `push` with `--force`, `-f` or a `+ref` | high; `--force-with-lease` medium |
| `git_push_delete` | `push --delete`, `-d` or `:branch` | high for main, master, trunk, develop, production; else medium |
| `git_reset_hard`, `git_clean` | `reset --hard`, `clean -f` | medium |
| `skip_hooks` | `--no-verify` on commit or push | low |
| `chmod_777` | chmod with mode 777 | medium |
| `disk_write` | `mkfs*`, `dd of=/dev/...` (not null, zero, stdout, stderr, tty) | high |
| `infra_destroy` | `terraform destroy`, `kubectl delete`, `helm uninstall` | medium |
| `destructive_sql` | DROP TABLE/DATABASE/SCHEMA/INDEX/VIEW, TRUNCATE TABLE (high), DELETE FROM without WHERE (medium) | see left |
| `pipe_to_shell` | curl or wget piped into a shell | high |
| `sudo` | any segment using sudo | low |
| `secret_file` | path or word naming a secret file | high or medium |

SQL rules in Bash only apply when a SQL client (psql, mysql, mariadb, sqlite3, sqlcmd, mycli, pgcli, clickhouse-client) appears in the command, so `git commit -m 'drop table x'` is not flagged. Non-Bash tools are checked for `query` and `sql` input fields and for path fields (`file_path`, `path`, `notebook_path`).

`secret_file_severity(name, pathlike)` mirrors Flockdeck's auto-review name check: `.git-credentials`, SSH key names, key-like suffixes (.pem, .key, .p12, .pfx, .ppk, .keystore, .jks) and names containing "credential" are high; `.env`, `.env.*`, `.npmrc`, `.netrc`, `.pgpass` are medium; `.example`, `.sample`, `.template` and `.dist` files are exempt. A bare word from a command only matches exact secret file names. Summaries are whitespace-collapsed and clipped to 160 characters.
