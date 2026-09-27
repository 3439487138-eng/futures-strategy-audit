# Security and publication boundary

The excluded source directory contains a hard-coded legacy Tushare credential. It is treated as exposed and should be rotated by its owner. Its value was never copied into this repository, logs, tests, reports, commits, or workflow configuration.

This project requires no secret. `.env` is ignored and `.env.example` intentionally contains no credential variable. Production inputs are legal, unauthenticated public exchange files.

The security scan rejects notebooks, tracked raw/normalized market data, credential-like literal assignments, and Windows user paths. The original source folder is outside this repository and must never be force-added.

