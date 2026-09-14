# Synology DS423+ installation

The recommended installation pulls the image directly from GitHub Container
Registry. Copy these files into one directory on the NAS:

- `docker-compose.yml`
- `pronote.env` (create it from `pronote.env.example`)
- an empty `data` directory

In DSM:

1. Install **Container Manager** from Package Center.
2. In File Station, create a folder such as
   `/volume1/docker/pronote-homework`, put `docker-compose.yml` and `pronote.env`
   inside it, and create its `data` subfolder.
3. Open **Container Manager > Project > Create**.
4. Use project name `pronote-homework`, select the folder from step 2, and use
   the existing `docker-compose.yml` as the project source.
5. Build/create the project, then start it. Container Manager pulls
   `ghcr.io/vidax/pronote-homework-exporter:latest` automatically.

The GitHub package must be public for an anonymous pull. If it is private,
authenticate the NAS once with a GitHub personal access token (classic) having
only `read:packages` permission:

```sh
echo 'YOUR_TOKEN' | sudo docker login ghcr.io -u vidax --password-stdin
```

Open `http://NAS-IP:855/` for the weekly web planner. It opens directly without
an API key because it is intended for use on your trusted home network. Each
homework card has a checkbox; its status is persisted in
`data/completions.json` on the NAS. New homework always starts as **Not done**.
After the student marks it **Done**, it stays done across Pronote refreshes
until somebody unchecks it; Pronote's own status is not used.

The protected JSON endpoint remains `http://NAS-IP:855/homework.json`. Send the
configured API key in the `X-API-Key` HTTP header.

IoT completion notifications are available in two ways:

- MQTT topic `pronote/homework/done` when `MQTT_HOST` is configured. Events are
  QoS 1 and non-retained.
- Protected polling endpoint `http://NAS-IP:855/v1/events`, with API key and
  `ETag` support.

When upgrading from V1, import the new image and redeploy the Project with the
updated YAML. Existing `pronote.env` files work unchanged; the completion and
MQTT event paths have safe defaults. Keep the `data` directory because it now
contains both the cached homework and the student's saved completion states.

When upgrading from V1.1.0, keep the same `data` directory. V1.1.1 automatically
migrates existing completion records away from Pronote's changing internal IDs.

## Publishing and updating from GitHub

The workflow in `.github/workflows/publish-container.yml` runs the tests and
publishes a Linux/AMD64 image whenever `main` is pushed. The moving image tag is:

```text
ghcr.io/vidax/pronote-homework-exporter:latest
```

The Compose file uses `pull_policy: always`, so every project redeployment
checks GitHub for a newer image. The `latest` tag does not replace an already
running container by itself. For a later update, redeploy the project in
Container Manager, or run from the project directory:

```sh
sudo docker compose pull pronote-homework
sudo docker compose up -d pronote-homework
```

The mounted `data` directory and `pronote.env` remain untouched during an image
update.
