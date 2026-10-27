# VPS-safe deployment and cleanup

The deployment boundary is immutable application code versus persistent shared data. Keep the database, uploads, secrets, and runtime cache under `/srv/recommendation-engine/shared/`; never copy them from a developer machine and never delete them during a release.

## One-time VPS layout

```bash
sudo install -d -m 0755 /srv/recommendation-engine/{releases,shared,shared/media,shared/cache}
sudo install -m 0600 /dev/null /srv/recommendation-engine/shared/.env
```

Put production values from `.env.example` into `shared/.env` directly on the VPS. Use PostgreSQL in production. Back up the database and `shared/media` before the first release or any migration.

## Upload code into a new release

Run locally from the repository. Replace the host and release identifier; the destination must be a new directory under `releases`:

```bash
RELEASE_ID="$(date -u +%Y%m%d%H%M%S)"
rsync -az --delete --exclude-from=deploy/rsync-excludes.txt ./ deploy@example.edu:/srv/recommendation-engine/releases/$RELEASE_ID/
```

`--delete` is safe here only because the target is a brand-new release directory. Never point this command at `shared`, `media`, the VPS application root, or an existing production checkout.

On the VPS, link persistent state, install dependencies, validate, migrate, collect static files, and then switch the `current` symlink atomically:

```bash
APP_ROOT=/srv/recommendation-engine
RELEASE_ID=replace-with-the-uploaded-id
RELEASE="$APP_ROOT/releases/$RELEASE_ID"
test -d "$RELEASE" && test ! -e "$RELEASE/.env" && test ! -e "$RELEASE/db.sqlite3"
ln -s "$APP_ROOT/shared/.env" "$RELEASE/.env"
ln -s "$APP_ROOT/shared/media" "$RELEASE/media"
python3 -m venv "$RELEASE/.venv"
"$RELEASE/.venv/bin/pip" install -r "$RELEASE/requirements.txt"
cd "$RELEASE"
"$RELEASE/.venv/bin/python" manage.py check --deploy
"$RELEASE/.venv/bin/python" manage.py migrate --plan
"$RELEASE/.venv/bin/python" manage.py migrate
"$RELEASE/.venv/bin/python" manage.py collectstatic --noinput
ln -sfn "$RELEASE" "$APP_ROOT/current.next"
mv -Tf "$APP_ROOT/current.next" "$APP_ROOT/current"
sudo systemctl restart recommendation-engine
sudo systemctl is-active --quiet recommendation-engine
curl --fail --silent https://example.edu/ops/health/ >/dev/null
```

If validation fails, do not switch `current`. If post-switch health fails, point `current` back to the previous release and restart the service. Database migrations require a tested backup/rollback plan; a code rollback does not automatically reverse schema changes.

## Safe old-release cleanup

The supplied cleanup script is a dry run by default and only targets old directories under `releases`:

```bash
APP_ROOT=/srv/recommendation-engine KEEP_RELEASES=5 bash scripts/vps_release_cleanup.sh
APP_ROOT=/srv/recommendation-engine KEEP_RELEASES=5 bash scripts/vps_release_cleanup.sh --apply
```

Review the dry-run paths before using `--apply`. The script does not touch `shared/.env`, `shared/media`, PostgreSQL, or `shared/cache`.

## Load and security verification

Run Django tests locally against the isolated test database:

```bash
python manage.py test --settings=config.test_settings
python manage.py check --deploy
```

Run load tests only against an approved staging environment with a dedicated test student enrolled in exactly the test course:

```bash
python -m pip install -r requirements-load.txt
export LOAD_TEST_USERNAME=staging-load-user
read -rsp 'Staging password: ' LOAD_TEST_PASSWORD && export LOAD_TEST_PASSWORD
export LOAD_TEST_COURSE_ID=123
locust -f tests/load/locustfile.py --host https://staging.example.edu --headless -u 25 -r 5 -t 5m --csv load-test-results/chat
```

Start at 25 users, inspect error rate and p95 latency, then increase gradually. Never load-test production without an explicit maintenance window and monitoring. Confirm that cross-course IDs return no session/data, deactivated users cannot log in, invitation emails contain only signed reset links, and logs contain no `.env`, SMTP password, API key, session cookie, or message content that policy forbids retaining.
