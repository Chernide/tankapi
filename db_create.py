'''
Core creation of database and tables for the tank api project.
'''

import sqlite3
from contextlib import closing
from pathlib import Path


database_path = Path(__file__).resolve().parent / 'tankapi.db'


def main():
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS tanks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            connection.execute('''
                CREATE TABLE IF NOT EXISTS tankdata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tank_id INTEGER,
                    temperature REAL,
                    ph REAL,
                    ammonia REAL,
                    nitrite REAL,
                    nitrate REAL,
                    alkalinity REAL,
                    shaky BOOLEAN,
                    note TEXT,
                    created_at TIMESTAMP,
                    FOREIGN KEY (tank_id) REFERENCES tanks (id)
                )
            ''')

            connection.execute('''
                CREATE TABLE IF NOT EXISTS tankevents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tank_id INTEGER,
                    event_type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP,
                    FOREIGN KEY (tank_id) REFERENCES tanks (id)
                )
            ''')

            tank_count = connection.execute(
                'SELECT COUNT(*) FROM tanks'
            ).fetchone()[0]
            if tank_count == 0:
                connection.executemany(
                    'INSERT INTO tanks (name, description) VALUES (?, ?)',
                    [
                        ('20g', 'Downstairs 20 gallon tank'),
                        ('10g', 'Upstairs 10 gallon tank'),
                    ],
                )

    print(f'Database initialized at {database_path}')


if __name__ == '__main__':
    main()
