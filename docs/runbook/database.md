# Database setup and migrations

IdleGrid uses MySQL 8 on the coordinator. The Dispatcher connects to the `idlegrid` database using
`IDLEGRID_DB_URL`; workers do not connect directly to MySQL. Do not put credentials in this file or in
source code.

## Create the Optuna database

Optuna uses a separate, empty database on the same MySQL server. In MySQL Workbench, run this as an
account allowed to create databases:

```sql
CREATE DATABASE IF NOT EXISTS idlegrid_optuna
  CHARACTER SET utf8mb4;
```

The database account and its privileges are managed separately. Set `IDLEGRID_OPTUNA_DB_URL` to a URL
that selects this database before enabling Optuna storage.

## Configure the application database

Set `IDLEGRID_DB_URL` in the environment to a SQLAlchemy URL for the `idlegrid` database, for example:

```text
mysql+pymysql://idlegrid:<password>@127.0.0.1:3306/idlegrid
```

In PowerShell, set it for the current terminal session without writing the credential to a config file:

```powershell
$env:IDLEGRID_DB_URL = 'mysql+pymysql://idlegrid:<password>@127.0.0.1:3306/idlegrid'
```

If the password contains URL-reserved characters, URL-encode it before placing it in the URL.

## Apply migrations

From the repository root, after installing the Dispatcher dependencies, run:

```powershell
python -m idlegrid.db.migrate
```

The runner applies `idlegrid/db/migrations/NNNN_*.sql` in filename order and records each successful
migration in `schema_migrations`. Re-running the command reports that the schema is up to date. To
override the environment URL for one invocation, pass `--db-url` followed by the database URL.

Never edit an applied migration. Add a new numbered SQL file for later schema changes.
