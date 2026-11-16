"""MySQL Connector helpers matching Version 1's database schema."""

import re
from contextlib import contextmanager
from datetime import datetime, timezone

import mysql.connector

MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DATABASE = "cscproject"
MYSQL_USER = "root"
MYSQL_PASSWORD ="root"


def connect_user_database(include_database=True):
    settings = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
    }
    if include_database:
        settings["database"] = MYSQL_DATABASE
    return mysql.connector.connect(**settings)


@contextmanager
def user_database_cursor():
    connection = connect_user_database()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def initialize_user_database():
    if not re.fullmatch(r"[A-Za-z0-9_]+", MYSQL_DATABASE):
        raise ValueError(
            "MYSQL_DATABASE can contain only letters, numbers, and underscores."
        )

    server = connect_user_database(include_database=False)
    try:
        cursor = server.cursor()
        try:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS `{}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci".format(
                    MYSQL_DATABASE
                )
            )
        finally:
            cursor.close()
    finally:
        server.close()

    with user_database_cursor() as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(30) NOT NULL UNIQUE,
                class_name VARCHAR(2) NOT NULL,
                password_hash VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS user_molecules (
                user_id INT NOT NULL,
                molecule_name VARCHAR(255) NOT NULL,
                search_count INT NOT NULL DEFAULT 1,
                last_searched DATETIME(6) NOT NULL,
                PRIMARY KEY (user_id, molecule_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )


def find_user(username):
    with user_database_cursor() as database:
        database.execute(
            """
            SELECT user_id, username, class_name, password_hash
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        return database.fetchone()


def create_user(username, password, class_name):
    with user_database_cursor() as database:
        database.execute(
            """
            INSERT INTO users (username, class_name, password_hash)
            VALUES (%s, %s, %s)
            """,
            (username, class_name, password),
        )
        return database.lastrowid


def list_molecule_names():
    with user_database_cursor() as database:
        database.execute(
            """
            SELECT DISTINCT molecule_name
            FROM user_molecules
            ORDER BY molecule_name
            """
        )
        return [row["molecule_name"] for row in database.fetchall()]


def remember_user_search(user_id, molecule_name):
    searched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with user_database_cursor() as database:
        database.execute(
            """
            INSERT INTO user_molecules (
                user_id, molecule_name, search_count, last_searched
            )
            VALUES (%s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE
                search_count = search_count + 1,
                last_searched = %s
            """,
            (user_id, molecule_name, searched_at, searched_at),
        )
