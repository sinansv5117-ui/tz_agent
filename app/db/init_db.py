from app.db.postgres import get_connection


def init_database() -> None:
    """Create the exact route, trip and infos tables if they do not exist."""
    schema = """
    CREATE TABLE IF NOT EXISTS route (
        route_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        route_name VARCHAR(150) NOT NULL,
        stops JSONB NOT NULL DEFAULT '[]'::jsonb,
        CONSTRAINT route_stops_array CHECK (jsonb_typeof(stops) = 'array')
    );

    CREATE TABLE IF NOT EXISTS trip (
        trip_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        route_id INTEGER NOT NULL,
        route_name VARCHAR(150) NOT NULL,
        bus_name VARCHAR(150) NOT NULL,
        stops_list JSONB NOT NULL DEFAULT '[]'::jsonb,
        CONSTRAINT fk_trip_route FOREIGN KEY (route_id)
            REFERENCES route(route_id) ON DELETE CASCADE,
        CONSTRAINT trip_stops_array CHECK (jsonb_typeof(stops_list) = 'array')
    );

    CREATE TABLE IF NOT EXISTS infos (
        info_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        message TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_trip_route_id ON trip(route_id);
    CREATE INDEX IF NOT EXISTS idx_route_name ON route(route_name);
    CREATE INDEX IF NOT EXISTS idx_trip_bus_name ON trip(bus_name);
    CREATE INDEX IF NOT EXISTS idx_infos_time ON infos(time);
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)


if __name__ == "__main__":
    init_database()
    print("PostgreSQL tables route, trip, and infos are ready.")
