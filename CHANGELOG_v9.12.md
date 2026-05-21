# CHANGELOG v9.12 — Redis Production Deployment Runbook

**Audit:** 114/114 PASS — **65th consecutive clean.**

## What

Ships `docs/REDIS_DEPLOYMENT_RUNBOOK.md` (~566 lines) — comprehensive deployment runbook operationalizing the v9.11 RedisBackend production-grade configuration for real Ecobank Kenya deployment context.

## Sections

1. **Topology choices** — decision matrix; recommended initial deployment (2-3 Streamlit + 1 Redis primary)
2. **TLS certificate setup** — public/internal/self-signed CA options; Redis 6+ TLS config; A2Z-side validation
3. **ACL configuration** — Redis 6+ user setup with `~a2z:*` key-prefix scoping; least-privilege command grants
4. **Monitoring** — 8 key metrics + thresholds; slowlog config; redis_exporter for Prometheus; Grafana dashboard recommendations
5. **Backup & DR** — RDB + AOF persistence; daily off-host backup script; DR procedures for primary loss / data loss / network partition
6. **Capacity planning** — A2Z keyspace estimates (~250-300 KB total); maxmemory + connection pool sizing
7. **Deployment checklist** — pre-flight, initial deployment, post-deployment validation
8. **Operational procedures** — manual key cleanup, version upgrade, emergency InMemoryBackend failover, connection-pool exhaustion troubleshooting
9. **Honest acknowledgements** — 10 explicit caveats (pilot-only self-signed CA, no Sentinel detail, etc.)

## Audience

- Joshua (decision-maker on topology and timing)
- Bank IT operations team (executes deployment + ongoing ops)
- Bank CISO (signs off on TLS / ACL / network topology)

## What v9.12 does NOT ship

1. No Kubernetes-specific deployment
2. No detailed Sentinel / Cluster topology setup
3. No bank-specific compliance (CBK Operations Resilience Guidelines / DPA 2019) lawyer review
4. No actual TLS certs or ACL passwords
5. No production-traffic load testing recipe (different concern from Redis ops)

## Honest acknowledgements

1. **Runbook is generic** — Ecobank-specific deployment may need additional bank-IT procedures Joshua should fold in.
2. **No live Redis to test against** — Claude couldn't run the deployment recipe end-to-end; Joshua's first deployment will validate.
3. **Capacity estimates** based on current state surfaces; v10.x additions would expand the footprint.
4. **Recovery SLAs** (RTO 5-30min, RPO up to 24h) reflect daily-backup baseline; tighter targets need replicated topology.
5. **Backup script is template** — bank's existing backup infrastructure may supersede.

## Next: v9.13

`scripts/redis_admin.py` operations CLI — health-check, key inventory, cross-process state verification, migration helpers. Operator-facing tool that makes Redis deployment debuggable from the command line.
