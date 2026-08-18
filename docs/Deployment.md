# Deployment



## Local development



Use Docker Compose for the integrated stack:



```bash

cp .env.example .env

docker compose up --build

```



Frontend: `http://localhost:3000`

Backend docs: `http://localhost:8002/docs`



## Health checks



- `GET /api/v1/healthz` — process liveness

- `GET /api/v1/readyz` — database readiness



## Production considerations



- Use environment-specific values for `DATABASE_URL`, `JWT_SECRET`, and S3 credentials.

- Configure container restarts and health checks in orchestration.



## Reverse proxy & TLS



`docker-compose.prod.yml` fronts `backend` and `frontend` with an `nginx`

service (`nginx/nginx.conf`); neither service publishes a port directly to

the host anymore.



Before first bringing up the prod stack, generate a TLS cert:



```bash

./nginx/generate-self-signed-cert.sh

```



This creates `nginx/certs/fullchain.pem` and `nginx/certs/privkey.pem`

(gitignored — generate per environment, don't commit them). Nginx redirects

all HTTP (port 80) traffic to HTTPS (port 443) and terminates TLS there.



This is currently a **self-signed cert** (no domain registered yet), so

browsers/clients will show an untrusted-certificate warning — expected for

now. Once a real domain exists, replace those two files with a CA-issued

cert (e.g. Let's Encrypt); no other config changes are needed.



```bash

docker compose -f docker-compose.prod.yml up --build -d

```



### Certificate renewal



Self-signed certs don't auto-renew the way Let's Encrypt's `certbot` does,

so `nginx/renew-cert-if-needed.sh` handles it: run on a schedule, it checks

the cert's remaining validity, regenerates it once within 30 days of

expiry, and reloads nginx gracefully (`nginx -s reload` — no dropped

connections) so the new cert takes effect without downtime.



Every run is logged to `nginx/certs/renewal.log`. On failure (cert

generation error, or nginx reload failure) it also logs an ERROR to

syslog via `logger`, and — if `CERT_ALERT_WEBHOOK_URL` is set in the

environment — POSTs a JSON alert there. The webhook is optional; leave it

unset and alerting still works via syslog alone.



Add it to the host's crontab (daily is enough given the 30-day threshold):



```bash

crontab -e

# add this line:

0 3 * * * cd /home/peach/NT-Incident-Management-System-IMS- && ./nginx/renew-cert-if-needed.sh >> nginx/certs/renewal.log 2>&1

```



To pick up alerts on failure, set the webhook once in the crontab or the

shell environment cron runs under:



```bash

CERT_ALERT_WEBHOOK_URL=https://hooks.example.com/... crontab -e

```



## Database



### Connection pooling



Configurable via `.env` (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,

`DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` — see `.env.example`). Defaults are

sized for a single backend replica; if you ever run more than one backend

container, keep `(DB_POOL_SIZE + DB_MAX_OVERFLOW) * replica_count`

comfortably under postgres's own `max_connections` (currently 100, set in

`docker-compose.prod.yml`).



### Backup



```bash

./scripts/db-backup.sh

```



Takes a `pg_dump` custom-format backup into `backups/` (gitignored — these

contain real data), deletes backups older than `RETENTION_DAYS` (default

14), and logs to `backups/backup.log`. On failure it logs to syslog and

optionally POSTs to `DB_BACKUP_ALERT_WEBHOOK_URL`, same pattern as the

cert renewal alerting above.



Add to crontab for a nightly backup:



```bash

crontab -e

# add:

0 2 * * * cd /home/peach/NT-Incident-Management-System-IMS- && ./scripts/db-backup.sh

```



### Restore



```bash

./scripts/db-restore.sh --file backups/ims_20260818_020000.dump --yes

```



Without `--yes`, prints what it would do and exits without changing

anything. Without `--target-db`, restores into the **live** database

(destructive — existing data is dropped and replaced by `--clean

--if-exists`). Pass `--target-db <name>` to restore into a different

database instead, e.g. for testing.



### Restore testing



Having a backup file isn't the same as knowing it actually restores.

`scripts/db-restore-test.sh` proves it does: it restores the latest (or a

given) backup into a disposable `${POSTGRES_DB}_restore_test` database

(never the live one), checks the table count matches the live database's

and that core tables are queryable, then drops the scratch database.



```bash

./scripts/db-restore-test.sh

# or test a specific backup:

./scripts/db-restore-test.sh backups/ims_20260810_020000.dump

```



Recommended weekly, after backups have had time to accumulate:



```bash

crontab -e

# add:

0 4 * * 0 cd /home/peach/NT-Incident-Management-System-IMS- && ./scripts/db-restore-test.sh

```



### Index verification



```bash

./scripts/db-index-usage.sh

```



Reports real usage from postgres's own stats (`pg_stat_user_indexes`,

`pg_stat_user_tables`) — indexes with zero scans, and tables with more

sequential scans than index scans. Run this after the system has seen

real production traffic, not right after a fresh deploy (everything

legitimately shows 0 scans then). Stats reset on a postgres restart, so

judge trends over a real traffic window.