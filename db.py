import psycopg2

import config

def connect_to_db(create=False):
    conn = psycopg2.connect(**config.DB)
    cursor = conn.cursor()
    if create:
        #cursor.execute("CREATE DATABASE IF NOT EXISTS mlb")
        cursor.execute("CREATE TABLE IF NOT EXISTS submissions (hash_id varchar PRIMARY KEY)")
        cursor.execute("CREATE TABLE IF NOT EXISTS comments (hash_id varchar PRIMARY KEY)")
        conn.commit()

    return conn, cursor

def check_hash_exists(table_name, hash_id, cursor):
    cursor.execute("SELECT hash_id FROM {} WHERE hash_id = '{}';".format(table_name, hash_id))
    match = cursor.fetchone()
    return match
