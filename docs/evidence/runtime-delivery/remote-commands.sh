set -euo pipefail
export PG_BIN=/absolute/path/to/trusted-tools/postgresql-16.15/bin
export NGINX_BIN=/absolute/path/to/trusted-tools/nginx-1.30.5/sbin/nginx
date -u; git rev-parse HEAD; git status --short
.venv/bin/ruff check apps/api tests scripts
npm run test:admin
npm run test:dom
npm run test:native
npm run typecheck
npm run build
.venv/bin/python scripts/test_with_postgres.py
.venv/bin/python scripts/e2e_with_postgres.py --http-only --native-client --dom-client
.venv/bin/python scripts/backup_restore_drill.py
.venv/bin/python scripts/linux_delivery_check.py --skip-systemd
.venv/bin/python scripts/benchmark_daily.py --baseline-ref adaef77da60fcd88513fcb97d54e6d801dd2729f --output /tmp/runtime-remote-benchmark.json
.venv/bin/python scripts/upgrade_drill.py --old-ref 640148dd84d6241eea399ccfc5552d0d324fc001 --output /tmp/runtime-remote-upgrade.json
.venv/bin/python scripts/check_dev_stack.py
git status --short; date -u
printf '\nRUNTIME_EXACT_SHA_ALL_PASS exit=0\n'
