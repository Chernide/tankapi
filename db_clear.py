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
                DELETE FROM tankdata;
            ''')

            connection.execute('''
                DELETE FROM tankevents;
            ''')

    print(f'Database cleared at {database_path}')


if __name__ == '__main__':
    main()
