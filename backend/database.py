"""Fixed, read-only queries used by the database browser, separate from the agent."""
import sqlite3
from contextlib import closing
from pathlib import Path
from .schemas import DatabaseView


def read_city_database(path: Path, page=1, page_size=20, search="") -> DatabaseView:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        term = f"%{search}%"
        where = "WHERE city_name LIKE ? OR state LIKE ?"
        total = connection.execute(
            f"SELECT COUNT(*) FROM city_stats {where}", (term, term)
        ).fetchone()[0]
        stats = connection.execute(
            "SELECT COALESCE(SUM(population), 0), COUNT(DISTINCT state) FROM city_stats"
        ).fetchone()
        rows = connection.execute(
            f"SELECT city_name, population, state FROM city_stats {where} "
            "ORDER BY population DESC, city_name LIMIT ? OFFSET ?",
            (term, term, page_size, (page - 1) * page_size),
        ).fetchall()
        return DatabaseView(
            table="city_stats", columns=["city_name", "population", "state"],
            rows=[dict(row) for row in rows], total=total,
            total_population=stats[0], states=stats[1], page=page, page_size=page_size,
        )
