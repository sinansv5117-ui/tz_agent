-- Travelzync PostgreSQL schema. This matches the requested table design.

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

-- Optional sample data. Uncomment only if you want to insert sample records.
-- WITH new_route AS (
--     INSERT INTO route (route_name, stops)
--     VALUES (
--         'Malappuram to Kozhikode',
--         '["Malappuram", "Ramanattukara", "Kozhikode"]'::jsonb
--     ) RETURNING route_id, route_name
-- )
-- INSERT INTO trip (route_id, route_name, bus_name, stops_list)
-- SELECT route_id, route_name, 'KSRTC Express',
--        '[{"stop":"Malappuram","time":"08:00"},
--          {"stop":"Ramanattukara","time":"08:45"},
--          {"stop":"Kozhikode","time":"09:15"}]'::jsonb
-- FROM new_route;
-- INSERT INTO infos (message) VALUES ('[INFO] Bus service delayed by 15 minutes');
