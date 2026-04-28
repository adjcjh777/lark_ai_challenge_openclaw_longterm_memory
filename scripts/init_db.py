from memory_engine.db import connect, db_path_from_env, init_db


def main() -> None:
    db_path = db_path_from_env()
    conn = connect(db_path)
    init_db(conn)
    print(f"initialized {db_path}")


if __name__ == "__main__":
    main()
