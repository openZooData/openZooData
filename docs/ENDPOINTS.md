# openZooData — Admin Endpoints Referenz

Alle unter /api/v1/admin/ — Auth: super_admin sofern nicht anders angegeben.

## Gruppe A — RBAC-Fixtures (Blocker für test_rbac.py)

| Method | Endpoint | Auth | Beschreibung |
|---|---|---|---|
| POST | /api/v1/admin/zoos | super_admin | Zoo anlegen (reaktiviert deaktivierte Slugs) |
| DELETE | /api/v1/admin/zoos/<zoo> | super_admin | Zoo deaktivieren |
| POST | /api/v1/admin/tenants | super_admin | Tenant anlegen |
| DELETE | /api/v1/admin/tenants/<id> | super_admin | Tenant deaktivieren |
| POST | /api/v1/admin/tenants/<id>/zoos | super_admin | Zoo Tenant zuordnen (ein Zoo = ein Tenant) |
| DELETE | /api/v1/admin/tenants/<id>/zoos/<zoo> | super_admin | Zuordnung entfernen |
| POST | /api/v1/admin/users/<id>/roles/zoo | super_admin / tenant_admin | Zoo-Rolle vergeben |
| DELETE | /api/v1/admin/users/<id>/roles/zoo/<zoo>/<role> | super_admin / tenant_admin | Zoo-Rolle entziehen |
| POST | /api/v1/admin/users/<id>/roles/tenant | super_admin | Tenant-Rolle vergeben |
| DELETE | /api/v1/admin/users/<id>/roles/tenant/<tenant_id> | super_admin | Tenant-Rolle entziehen |
| DELETE | /api/v1/admin/users/<id> | super_admin | User deaktivieren |

## Gruppe B — Admin-UI (Phase 3)

| Method | Endpoint | Auth | Beschreibung |
|---|---|---|---|
| GET | /api/v1/admin/zoos | super_admin | Zoo-Liste |
| GET | /api/v1/admin/zoos/<zoo> | super_admin | Zoo-Details |
| PUT | /api/v1/admin/zoos/<zoo> | super_admin | Zoo bearbeiten |
| GET | /api/v1/admin/tenants | super_admin | Tenant-Liste |
| GET | /api/v1/admin/tenants/<id> | super_admin / tenant_admin | Tenant-Details |
| PUT | /api/v1/admin/tenants/<id> | super_admin | Tenant bearbeiten |
| GET | /api/v1/admin/users | super_admin | User-Liste (?tenant_id=) |
| GET | /api/v1/admin/users/<id> | super_admin | User-Details + alle Rollen |
| PUT | /api/v1/admin/users/<id> | super_admin | User bearbeiten |
| POST | /api/v1/admin/users/<id>/roles/global | super_admin | Globale Rolle vergeben |
| DELETE | /api/v1/admin/users/<id>/roles/global/<role> | super_admin | Globale Rolle entziehen |
| GET | /api/v1/admin/settings | super_admin | System-Settings lesen |
| PUT | /api/v1/admin/settings/<key> | super_admin | System-Setting schreiben |
| GET | /api/v1/admin/audit | super_admin | Audit-Log lesen |
| GET | /api/v1/admin/proposals | super_admin / moderator | Species-Proposals |
| PUT | /api/v1/admin/proposals/<id>/approve | super_admin / moderator | Proposal genehmigen (Moderator aktuell global) |
| PUT | /api/v1/admin/proposals/<id>/reject | super_admin / moderator | Proposal ablehnen |

## Password-Reset (öffentlich)

| Method | Endpoint | Auth | Beschreibung |
|---|---|---|---|
| POST | /api/v1/auth/password-reset/request | — | Reset anfordern (5/min) |
| POST | /api/v1/auth/password-reset/confirm | — | Reset bestätigen (10/min) |

## Dateien

```
admin_v6.py              ← nach routes/admin.py deployen
app_py_additions.txt     ← 2 Zeilen in app.py einfügen
auth_py_addition.py      ← _send_reset_email in routes/auth.py ergänzen
```

## Deployment-Reihenfolge

1. SQL-Migration ausführen (Postico):
   ```sql
   -- Prüfen: SELECT zoo_id, COUNT(*) FROM auth.tenant_zoos GROUP BY zoo_id HAVING COUNT(*) > 1;
   -- Erwartung: 0 Zeilen
   ```
   Dann `migrate_tenant_zoos_unique.sql` ausführen.

2. Dateien deployen:
   ```bash
   cp authz_v2.py ~/api/openZooData/source/helpers/authz.py
   cp admin_v6.py ~/api/openZooData/source/routes/admin.py
   ```

3. app.py ergänzen (app_py_additions.txt)

4. Gunicorn neustarten:
   ```bash
   ./restart_api.sh
   ```

5. Smoke-Test:
   ```bash
   # Deaktivierter super_admin mit altem Token muss 403 liefern
   curl -H "Authorization: Bearer <old_token>" https://api.openzoodata.org/api/v1/admin/users
   ```

## Deployment

```bash
# 1. admin.py nach source/routes/ kopieren
cp admin_v6.py ~/api/openZooData/source/routes/admin.py

# 2. In source/app.py einfügen (app_py_additions.txt):
#    from routes.admin import admin_bp
#    app.register_blueprint(admin_bp)

# 3. In source/routes/auth.py ergänzen:
#    _send_reset_email Funktion am Ende einfügen

# 4. Gunicorn neustarten
./restart_api.sh
```
