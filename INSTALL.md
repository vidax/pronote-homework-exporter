# Installation

This service runs as a single Linux/AMD64 container on a Synology DS423+ or any
Docker host. It stores homework and student completion status in a mounted
`data` directory, outside the container image.

## Synology DS423+

Download these three files from the repository's `synology` directory into
`/volume1/docker/pronote-homework`:

- `docker-compose.yml`
- `.env.example`
- `INSTALL.md` (optional offline reference)

Create the private configuration and persistent data directory:

```sh
cd /volume1/docker/pronote-homework
cp .env.example pronote.env
mkdir -p data
```

Edit `pronote.env` and replace the Pronote URL, username, password, and API key.
Generate the API key on a Mac or Linux computer with:

```sh
openssl rand -hex 24
```

Do not rename or commit `pronote.env`. It contains credentials and is excluded
from both Git and the Docker build context.

If the GitHub container package is private, authenticate the NAS before creating
the project:

```sh
sudo docker login ghcr.io -u vidax
```

Paste a GitHub personal access token (classic) with only `read:packages` at the
password prompt. A public container package needs no login.

In DSM, open **Container Manager > Project > Create**, select the directory,
and choose its `docker-compose.yml`. Start the project, then open:

```text
http://NAS-IP:855/
```

The machine-readable endpoint is `http://NAS-IP:855/homework.json` and requires
the configured API key in the `X-API-Key` header.

## Updating

The Compose file uses `ghcr.io/vidax/pronote-homework-exporter:latest`. Redeploy
the project in Container Manager, or update over SSH:

```sh
cd /volume1/docker/pronote-homework
sudo docker compose pull pronote-homework
sudo docker compose up -d pronote-homework
```

Never delete `pronote.env` or `data` during an update. The mounted directory
contains the cached homework and persistent Done/To do states.

For additional Synology details, see [`synology/INSTALL.md`](synology/INSTALL.md).
