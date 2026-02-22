import os
import sys
import psycopg2


def get_conn():
    # Preferat: un singur string (ideal și pentru Kubernetes Secret)
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn)

    # Alternativ: variabile separate
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    missing = [k for k, v in {
        "DB_HOST": host, "DB_NAME": name, "DB_USER": user, "DB_PASSWORD": password
    }.items() if not v]
    if missing:
        raise RuntimeError(
            "Missing env vars. Set DATABASE_URL or: " + ", ".join(missing)
        )

    return psycopg2.connect(
        host=host, port=int(port), dbname=name, user=user, password=password
    )


def init_db(conn):
    with conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)


def add_item(conn, name: str):
    with conn, conn.cursor() as cur:
        cur.execute("INSERT INTO items (name) VALUES (%s);", (name,))


def list_items(conn):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, created_at FROM items ORDER BY id;")
        for _id, name, created_at in cur.fetchall():
            print(f"{_id}. {name} ({created_at})")


def usage():
    print('Usage:\n  python3 app.py init\n  python3 app.py add "lapte"\n  python3 app.py list')


def main():
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    cmd = sys.argv[1]

    conn = get_conn()
    try:
        if cmd == "init":
            init_db(conn)
            print("OK")
        elif cmd == "add":
            if len(sys.argv) < 3:
                print('Missing item. Example: python3 app.py add "lapte"')
                sys.exit(1)
            init_db(conn)
            add_item(conn, sys.argv[2])
            print("Added")
        elif cmd == "list":
            init_db(conn)
            list_items(conn)
        else:
            usage()
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
