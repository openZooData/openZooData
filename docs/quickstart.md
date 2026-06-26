# Quick Start

> Local setup guide for OpenZooData.

This guide describes a minimal local setup for developers and evaluators.

---

## Requirements

- Python 3.11+
- PostgreSQL
- Git
- `pip`
- Optional: `venv`
- Optional: `gunicorn` for production-style testing

---

## 1. Clone Repository

```bash
git clone https://github.com/openZooData/openZooData
cd openZooData
```

---

## 2. Create Databases

OpenZooData uses two PostgreSQL databases:

| Database | Purpose |
|---|---|
| `openZooData` | Zoo, species, enclosure and publishing data |
| `openZooData_auth` | Users, roles, tokens and authentication |

Create them:

```sql
CREATE DATABASE "openZooData";
CREATE DATABASE "openZooData_auth";
```

---

## 3. Apply Schemas

```bash
psql -d openZooData -f source/schema/zoo_schema.sql
psql -d openZooData_auth -f source/schema/auth_schema.sql
```

---

## 4. Configure Environment

```bash
cp source/env.example source/.env
```

Edit `source/.env`:

```env
PG_HOST=localhost
PG_PORT=5432
PG_NAME=openZooData
PG_USER=postgres
PG_PASSWORD=change-me

AUTH_HOST=localhost
AUTH_PORT=5432
AUTH_NAME=openZooData_auth
AUTH_USER=postgres
AUTH_PASSWORD=change-me

JWT_SECRET=change-me
```

Use strong secrets in production.

---

## 5. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 6. Install Dependencies

Depending on repository layout:

```bash
pip install -r requirements.txt
```

or:

```bash
pip install -r source/requirements.txt
```

---

## 7. Start Development Server

```bash
PYTHONPATH=source python source/app.py
```

---

## 8. Start with Gunicorn

```bash
PYTHONPATH=source gunicorn --bind 127.0.0.1:5001 app:app
```

---

## 9. Test Health Endpoint

```bash
curl http://127.0.0.1:5001/status
```

Expected minimal response:

```json
{
  "status": "ok"
}
```

---

## 10. Create First Super Admin

Generate password hash:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw('YourPassword123!'.encode(), bcrypt.gensalt()).decode())"
```

Insert user:

```sql
BEGIN;

INSERT INTO auth.users (
    email,
    password_hash,
    is_active,
    must_change_password
)
VALUES (
    'your@email.com',
    '$2b$12$...hash...',
    TRUE,
    FALSE
)
RETURNING id;

INSERT INTO auth.user_global_roles (user_id, role)
VALUES (<id>, 'super_admin');

COMMIT;
```

---

## 11. Run Smoke Tests

```bash
cp tests/.env.example tests/.env
pip install -r tests/requirements-dev.txt

pytest tests/ -v -m "not slow and not write and not feedback and not requires_data and not media and not jwt"
```

---

## Troubleshooting

### Permission denied when running a script

Use:

```bash
python3 source/tools/script_name.py
```

or make it executable:

```bash
chmod +x source/tools/script_name.py
```

---

### Module import errors

Start commands with:

```bash
PYTHONPATH=source
```

Example:

```bash
PYTHONPATH=source python source/app.py
```

---

### Database connection fails

Check:

- database names,
- user permissions,
- `.env` location,
- PostgreSQL service,
- host and port.

---

### Health status degraded

A degraded health status usually means at least one dependency is not reachable.

Check:

- zoo database,
- auth database,
- media directory,
- SQLite export directory,
- environment variables.

---

## Production Notes

A typical production deployment uses:

```text
Apache / Reverse Proxy
      │
      ▼
Gunicorn
      │
      ▼
OpenZooData Flask App
      │
      ├── PostgreSQL Zoo DB
      ├── PostgreSQL Auth DB
      └── Media Directory
```

Recommended:

- enforce HTTPS,
- use a non-root service user,
- configure regular PostgreSQL backups,
- protect health detail endpoints,
- rotate JWT secrets if compromised,
- use rate limiting,
- monitor `/status`.
