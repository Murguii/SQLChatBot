"""Initialize a sample SQLite database for a music store demo."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def init_db(db_path: Path) -> None:
	data_dir = db_path.parent
	data_dir.mkdir(parents=True, exist_ok=True)

	with sqlite3.connect(db_path) as conn:
		cursor = conn.cursor()

		cursor.executescript(
			"""
			DROP TABLE IF EXISTS sales;
			DROP TABLE IF EXISTS tracks;
			DROP TABLE IF EXISTS albums;
			DROP TABLE IF EXISTS artists;

			CREATE TABLE artists (
				id INTEGER PRIMARY KEY,
				name TEXT NOT NULL
			);

			CREATE TABLE albums (
				id INTEGER PRIMARY KEY,
				title TEXT NOT NULL,
				artist_id INTEGER NOT NULL,
				FOREIGN KEY (artist_id) REFERENCES artists (id)
			);

			CREATE TABLE tracks (
				id INTEGER PRIMARY KEY,
				name TEXT NOT NULL,
				album_id INTEGER NOT NULL,
				genre TEXT NOT NULL,
				unit_price REAL NOT NULL,
				duration_ms INTEGER NOT NULL,
				FOREIGN KEY (album_id) REFERENCES albums (id)
			);

			CREATE TABLE sales (
				id INTEGER PRIMARY KEY,
				track_id INTEGER NOT NULL,
				quantity INTEGER NOT NULL,
				sale_date TEXT NOT NULL,
				customer_name TEXT NOT NULL,
				FOREIGN KEY (track_id) REFERENCES tracks (id)
			);
			"""
		)

		artists = [
			(1, "Radiohead"),
			(2, "Daft Punk"),
			(3, "Fleetwood Mac"),
			(4, "Nirvana"),
			(5, "Taylor Swift"),
			(6, "The Beatles"),
			(7, "Adele"),
			(8, "Coldplay"),
		]

		albums = [
			(1, "OK Computer", 1),
			(2, "In Rainbows", 1),
			(3, "Discovery", 2),
			(4, "Random Access Memories", 2),
			(5, "Rumours", 3),
			(6, "Nevermind", 4),
			(7, "1989", 5),
			(8, "Abbey Road", 6),
			(9, "25", 7),
			(10, "A Rush of Blood to the Head", 8),
		]

		tracks = [
			(1, "Paranoid Android", 1, "Alternative", 1.29, 386000),
			(2, "Karma Police", 1, "Alternative", 1.29, 262000),
			(3, "Weird Fishes", 2, "Alternative", 1.19, 318000),
			(4, "Reckoner", 2, "Alternative", 1.19, 290000),
			(5, "One More Time", 3, "Electronic", 1.39, 320000),
			(6, "Harder Better Faster Stronger", 3, "Electronic", 1.39, 224000),
			(7, "Get Lucky", 4, "Electronic", 1.49, 369000),
			(8, "Instant Crush", 4, "Electronic", 1.49, 337000),
			(9, "Dreams", 5, "Rock", 1.29, 257000),
			(10, "The Chain", 5, "Rock", 1.29, 270000),
			(11, "Smells Like Teen Spirit", 6, "Grunge", 1.29, 301000),
			(12, "Come As You Are", 6, "Grunge", 1.29, 219000),
			(13, "Blank Space", 7, "Pop", 1.29, 231000),
			(14, "Style", 7, "Pop", 1.29, 231000),
			(15, "Come Together", 8, "Rock", 1.29, 259000),
			(16, "Something", 8, "Rock", 1.29, 183000),
			(17, "Hello", 9, "Pop", 1.29, 295000),
			(18, "When We Were Young", 9, "Pop", 1.29, 290000),
			(19, "Clocks", 10, "Alternative", 1.29, 307000),
			(20, "The Scientist", 10, "Alternative", 1.29, 309000),
		]

		sales = [
			(1, 1, 2, "2024-01-05", "Laura Hill"),
			(2, 5, 1, "2024-01-12", "Marco Diaz"),
			(3, 9, 3, "2024-02-02", "Emily Chen"),
			(4, 11, 2, "2024-02-15", "Sam Carter"),
			(5, 13, 1, "2024-02-20", "Nina Patel"),
			(6, 15, 4, "2024-03-01", "Jordan Lee"),
			(7, 7, 2, "2024-03-08", "Olivia Perez"),
			(8, 3, 1, "2024-03-12", "Daniel Kim"),
			(9, 17, 2, "2024-03-18", "Ana Torres"),
			(10, 19, 1, "2024-03-23", "George Martin"),
			(11, 2, 2, "2024-04-04", "Sofia Rossi"),
			(12, 6, 3, "2024-04-11", "Maya Singh"),
			(13, 10, 1, "2024-04-19", "Liam Walker"),
			(14, 12, 2, "2024-04-22", "Isabella Novak"),
			(15, 14, 1, "2024-04-27", "Rafael Costa"),
			(16, 8, 1, "2024-05-02", "Hannah Brooks"),
			(17, 18, 2, "2024-05-10", "Mateo Cruz"),
			(18, 20, 3, "2024-05-15", "Chloe Adams"),
			(19, 4, 1, "2024-05-20", "Victor Nguyen"),
			(20, 16, 2, "2024-05-25", "Elena Fischer"),
		]

		cursor.executemany("INSERT INTO artists VALUES (?, ?)", artists)
		cursor.executemany("INSERT INTO albums VALUES (?, ?, ?)", albums)
		cursor.executemany("INSERT INTO tracks VALUES (?, ?, ?, ?, ?, ?)", tracks)
		cursor.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", sales)

		conn.commit()


if __name__ == "__main__":
	init_db(Path("data/database.sqlite"))
