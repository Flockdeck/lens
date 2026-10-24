# Known gotchas

* [PyInstaller cannot cross-compile](build-needs-native-runner.md) - Each platform's binary is built on a runner of that platform; Windows on arm64 is allowed to fail.
* [Claim fencing and statement order](claim-fencing-and-lock-order.md) - Item updates are conditional on the claim token, and item rows are touched before the batch row.
* [Cleanup lock is per process](cleanup-lock-is-per-process.md) - The code and docstrings disagree about a database lock; the guard is an in-process asyncio lock.
* [Published versions are immutable and cached for a year](downloads-are-immutable.md) - publish-downloads refuses to replace a published version with different files and never moves latest backwards.
* [Enricher construction runs in a thread](enricher-built-off-the-event-loop.md) - Building an HTTP client loads TLS certificates, which can take seconds and would freeze the UI on the event loop.
* [Frozen binary specifics](frozen-binary-startup.md) - freeze_support, an unpacked launcher, a data-directory path with a space, and files read from the bundle.
* [Killing the launcher can orphan the server](launcher-kill-orphans-server.md) - The packaged program is a launcher plus a child; a hard kill of the launcher would leave the child holding the port and database.
* [The parser is deliberately lenient](lenient-parsing.md) - Bad lines, a cut last line, unknown fields and unknown event types are tolerated; only another version number or no events fails.
* [Logs go to a file when stdout is a pipe](log-file-when-piped.md) - With LOG_FILE unset and no terminal, logs are written to lens.log so an unread pipe cannot freeze the server.
* [Timestamps are naive UTC](naive-utc-timestamps.md) - Database datetimes are stored without a timezone but always mean UTC.
* [Sessions without started_at](null-started-at.md) - Date filters exclude them; trends fall back to created_at.
* [Failed uploads can leave unreferenced files](orphan-files-after-failed-upload.md) - The file is stored before its row is written, so a later failure leaves an orphan file but never a dangling row.
* [Re-uploading a session overwrites it](reupload-supersedes-session.md) - A recording with an existing session id replaces the stored session in place, and identical content skips re-enrichment.
* [SQLite write transactions begin immediately](sqlite-begin-immediate.md) - Writers use BEGIN IMMEDIATE and readers BEGIN deferred so writers queue and reads never hold the write lock.
* [status_seconds are upper bounds](status-seconds-upper-bound.md) - Time in each pane status can overstate working and blocked time.
* [Zero permission counts can mean not recorded](transcript-metrics-not-recorded.md) - Transcript-format recordings have no permission or status lines, so their zero counts are not evidence.
* [UI limits mirror server defaults](ui-limits-mirror-server.md) - lib.js hard-codes 17 MiB and 100 files; changing the server settings does not change the UI pre-check.
* [Upload response lists names, not ids](upload-names-and-batch-order.md) - POST /batches echoes accepted file names; item ids come from GET /batches/{id}.
* [Windows extended path prefix](windows-extended-path-prefix.md) - Path.resolve() can return a prefixed path on Windows, so the store strips the prefix before comparing paths.
* [Windows reports access denied when a directory is being created](windows-mkdir-permission-error.md) - _mkdirs swallows PermissionError if the directory exists afterwards.
