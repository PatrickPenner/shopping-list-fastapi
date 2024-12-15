# Shopping List Fastapi

## Installation

### Dependencies

Install the pip dependencies from `requirements.txt`:
```shell
pip install -r requirements.txt
```

Note that psycopg2 has an external dependency on postgresql-dev (or libpq-dev).

### Database

Set up the database user by running:
```shell
psql -d postgres -h localhost -c "CREATE ROLE $USER WITH ENCRYPTED PASSWORD '$PASSWORD'; ALTER ROLE $USER WITH LOGIN CREATEDB;"
```

Set up the database by running:
```shell
psql -d postgres -h localhost -U $USER -c "CREATE DATABASE $DATABASE;"
```

where `$USER`, `$PASSWORD`, and `$DATABASE` are standins for your chosen values. The server will reade a `$DATABASE_URL` from the environment, which can be placed in, e.g., such a `.env` file:

```shell
# .env
export DATABASE_URL="postgresql+psycopg2://$USER:$PASSWORD@localhost:5432/$DATABASE"
```

### Auth

Set up JWT auth by adding these environment variables:
```shell
# .env
export SECRET_KEY=<your secret key>
export ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=30
```