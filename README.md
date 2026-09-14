# Pronote homework exporter

A small service for a NAS. It fetches homework from Pronote on a schedule,
converts it to a stable JSON format, and serves the last successful snapshot to
an E-ink device. Pronote access remains read-only; student completion marks are
stored locally on the NAS.

HTTP is the recommended transport: a sleeping device can wake, make one GET,
and disconnect. MQTT is optional; when configured, the same JSON is published
as a retained message to an existing Mosquitto broker.

This project uses the unofficial [PronotePy](https://github.com/bain3/pronotepy)
client. It is not affiliated with Index Education. Use it only with an account
you are authorized to access. Pronote can change its private protocol, so keep
the dependency and this service updated if fetching stops working.

## What it provides

- `GET /homework.json` and `GET /v1/homework`: the cached JSON document
- `GET /`: a five-column Monday–Friday web planner with week navigation; it
  opens without a key for trusted-LAN use
- `GET /planner.json`: the planner's unauthenticated LAN-only data source
- `POST /planner/homework/{id}/done`: persist a student's local done status
- `GET /healthz`: public liveness check without personal information
- `GET /v1/status`: authenticated refresh diagnostics
- `GET /v1/events`: authenticated, ETag-aware completion event feed for IoT
- Atomic disk updates: a failed refresh preserves the previous snapshot
- `ETag` support: the E-ink client can skip parsing/redrawing unchanged data
- Optional retained MQTT publication after each successful fetch
- Password, ENT, parent-account child selection, and renewable token login

The JSON contract is versioned and deliberately independent from PronotePy.
See [examples/homework.json](examples/homework.json).

## NAS quick start with Docker Compose

1. Copy the sample configuration and create the data directory:

   ```sh
   cp .env.example .env
   mkdir -p data
   ```

2. Edit `.env`. At minimum, set the full Pronote URL, username, password, and a
   long random `API_KEY` (for example, from `openssl rand -hex 24`). The URL normally ends with `eleve.html` or
   `parent.html`. For a parent account with more than one child, set
   `PRONOTE_CHILD_NAME` to the exact name shown by Pronote.

3. Start the service:

   ```sh
   docker compose up -d --build
   docker compose logs -f pronote-homework
   ```

4. Retrieve the snapshot from another machine:

   ```sh
   curl -H 'X-API-Key: your-key' http://nas.local:8080/homework.json
   ```

   Or open `http://nas.local:8080/` in a browser for the weekly planner. The
   planner does not ask for the API key.

The JSON is also written to `data/homework.json`. The service refreshes every
15 minutes by default and fetches the previous 7 days through the next 21 days. A minimum
five-minute interval is enforced to avoid excessive requests to Pronote.

## Student completion status

Every homework card in the web planner has a **Not done / Done** checkbox. A
change is saved immediately to `data/completions.json`, so it survives page
reloads, container restarts, image upgrades, and later Pronote refreshes. This
is a local planner status: it does not mark the assignment as done in Pronote.

The browser uses this trusted-LAN endpoint:

```http
POST /planner/homework/123456/done
Content-Type: application/json

{"done":true}
```

The endpoint is intentionally unauthenticated like the planner itself. It
accepts JSON only, which prevents ordinary cross-origin form submissions.

## Login choices

### Direct Pronote or ENT password

Keep `PRONOTE_AUTH_MODE=password`. A direct Pronote account needs no other
setting. If the URL redirects through an ENT, set `PRONOTE_ENT` to the matching
function from the [PronotePy ENT list](https://pronotepy.readthedocs.io/en/stable/api/ent.html).
Some ENT/EduConnect flows change independently and may require a future
PronotePy update.

Secrets can be supplied as Docker secrets instead of literal environment
values by setting `PRONOTE_USERNAME_FILE`, `PRONOTE_PASSWORD_FILE`,
`PRONOTE_ACCOUNT_PIN_FILE`, `API_KEY_FILE`, or `MQTT_PASSWORD_FILE`.

### Renewable token (recommended after initial setup)

Token mode lets the running service avoid retaining the normal account
password. With password authentication configured and working, run:

```sh
docker compose run --rm pronote-homework create-token
```

This writes `data/credentials.json` with mode `0600`. Then change `.env` to:

```dotenv
PRONOTE_AUTH_MODE=token
PRONOTE_USERNAME=
PRONOTE_PASSWORD=
```

Token credentials are still sensitive. Pronote rotates them on login, and the
service replaces the credential file atomically after every successful login.

## Existing Mosquitto broker

Set `MQTT_HOST` (and credentials if needed). No broker is bundled because the
NAS already has one. The service publishes the complete snapshot to
`pronote/homework` by default using QoS 1 and `retain=true`.

Test it with:

```sh
mosquitto_sub -h nas.local -t pronote/homework -C 1
```

MQTT publication failure does not remove or invalidate the HTTP snapshot.

When a homework changes from not done to done, the service also publishes a
non-retained event to `pronote/homework/done` by default. Each event includes a
unique `event_id`, timestamp, and homework details. MQTT QoS 1 consumers should
remember `event_id` to avoid activating a bell twice if the broker redelivers a
message.

An IoT device can alternatively poll the protected HTTP event feed:

```sh
curl -H 'X-API-Key: your-key' http://nas.local:8080/v1/events
```

Store the response `ETag` and send it as `If-None-Match` on the next poll. A
`304 Not Modified` response means no new done event has been recorded. The most
recent 100 done events are persisted with the completion states.

## E-ink client behavior

Store the `ETag` response header after a successful request. On the next wake,
send it back as `If-None-Match`. A `304 Not Modified` response means the
student and normalized homework content are unchanged and the display need not refresh.
The top-level `content_hash` changes only when the normalized homework array
changes; `generated_at` changes on every successful fetch.

Do not expose port 8080 directly to the internet: the web planner, its
`/planner.json` data source, and its status-update endpoint are intentionally
unauthenticated. Keep the service on the trusted LAN or access it through a
VPN. The E-ink and IoT read endpoints remain protected by `API_KEY`.

## Local commands

Python 3.11 or newer is required.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
set -a; . ./.env; set +a
pronote-homework once
pronote-homework serve
```

Run the dependency-free unit tests with:

```sh
python3 -m unittest discover -s tests -v
```
