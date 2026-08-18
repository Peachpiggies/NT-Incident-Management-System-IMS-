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