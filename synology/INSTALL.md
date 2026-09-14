# Synology DS423+ installation

Copy these files into one directory on the NAS:

- `pronote-homework-exporter-1.1.0-amd64.tar`
- `docker-compose.yml`
- `pronote.env` (create it from `pronote.env.example`)
- an empty `data` directory

In DSM:

1. Install **Container Manager** from Package Center.
2. Open **Container Manager > Image > Action > Import > Add from file** and
   select `pronote-homework-exporter-1.1.0-amd64.tar`.
3. In File Station, create a folder such as
   `/volume1/docker/pronote-homework`, put `docker-compose.yml` and `pronote.env`
   inside it, and create its `data` subfolder.
4. Open **Container Manager > Project > Create**.
5. Use project name `pronote-homework`, select the folder from step 3, and use
   the existing `docker-compose.yml` as the project source.
6. Build/create the project, then start it.

Open `http://NAS-IP:855/` for the weekly web planner. It opens directly without
an API key because it is intended for use on your trusted home network. Each
homework card has a checkbox; its status is persisted in
`data/completions.json` on the NAS.

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
