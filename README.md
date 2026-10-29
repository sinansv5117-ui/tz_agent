# Travelzync Multi-Tool AI Agent

Travelzync is a command-line bus travel assistant. It uses a Groq-hosted model through the OpenAI-compatible API, PostgreSQL route and trip data, and Python tools for route search, schedule lookup, and feedback collection.

Route finding remains the primary operation: the existing route search locates direct or connected journeys, then the schedule lookup optionally adds one database-backed boarding time for the first bus leg. Schedule lookup does not replace or alter route search.

## Features

- Finds direct bus journeys and forward-only journeys with transfers.
- Matches exact and alternate place spellings and applies fuzzy spelling correction against known route stops.
- Looks up one suitable scheduled boarding time at the starting stop of the first bus leg.
- Uses an explicitly requested time when the user gives one; otherwise compares schedules with current India-local time (`Asia/Kolkata`).
- Returns a route even when the schedule is missing or the schedule database query fails.
- Accepts user feedback through the complaint/information tool.
- Keeps greetings and small talk conversational without unnecessary tool calls.

Schedule times are static database schedules, not live vehicle locations or real-time arrival predictions. For transfer journeys, only the first bus time is looked up; connecting bus times are not calculated.

## Project structure

```text
travelzync_agent/
├── app/
│   ├── agent.py                    # LLM instructions, tool definitions and orchestration
│   ├── config.py                   # Environment-backed settings
│   ├── main.py                     # Command-line chat loop
│   ├── db/
│   │   ├── postgres.py             # PostgreSQL connection context manager
│   │   └── init_db.py              # Creates tables and indexes if absent
│   └── tools/
│       ├── bus_route_tool.py       # Existing route matching and route search
│       ├── schedule_tool.py        # First-leg scheduled time lookup
│       ├── complaint_tool.py       # Stores user feedback
│       └── rag_tool.py             # Placeholder; does not retrieve documents
├── sql/
│   └── schema.sql                 # PostgreSQL schema and optional sample inserts
├── tests/
│   ├── test_route_logic.py         # Route algorithm tests
│   └── test_schedule_lookup.py    # Schedule and integration tests
├── requirements.txt
├── run.ps1
└── README.md
```

## Requirements

- Python 3.10 or later (the application uses `zoneinfo`).
- PostgreSQL with a database created for Travelzync.
- A Groq API key and a model available to your Groq account.

Python packages are listed in `requirements.txt`: OpenAI client, Psycopg 3, python-dotenv, RapidFuzz, and pytest.

## Setup on Windows PowerShell

Open PowerShell in the project folder. Create and activate a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create `.env` in the project root and set your own database URL and Groq API key. Keep secrets out of source control.

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/bus_database
GROQ_API_KEY=YOUR_GROQ_API_KEY
GROQ_MODEL=openai/gpt-oss-20b
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

The application also supports these optional settings:

| Variable | Default | Description |
| --- | --- | --- |
| `TEMPERATURE` | `0.4` | Model response temperature. |
| `MAX_TOKENS` | `300` | Maximum model response tokens. |
| `MAX_ROUTE_HOPS` | `4` | Maximum number of bus legs in a connected route. |
| `MAX_ROUTE_RESULTS` | `50` | Maximum route options returned internally by route search. |

Create the tables and indexes, then start the interactive application:

```powershell
python -m app.db.init_db
python -m app.main
```

At the `You:` prompt, enter a travel question, for example `How do I get from Malappuram to Kozhikode?` or `Find a bus from Malappuram to Kozhikode after 9:00 AM`. Enter `exit` or `quit` to stop.

`run.ps1` is an optional helper, but if `.env` is missing it tries to copy `.env.example`. The project tree may not include that template file, so create `.env` manually using the variables above when needed. The direct commands above initialize and launch the app once dependencies and `.env` are configured.

## PostgreSQL database and tables

The application connects using `DATABASE_URL`. `app/db/init_db.py` creates the following tables and indexes with `IF NOT EXISTS`; it does not delete existing records. `CREATE TABLE IF NOT EXISTS` does not migrate an existing table whose columns differ, so compare an older database with `sql/schema.sql` before using it.

### `route`

One row represents an ordered route used by the route finder.

| Column | Type | Meaning |
| --- | --- | --- |
| `route_id` | `INTEGER` identity, primary key | Route identifier referenced by trips. |
| `route_name` | `VARCHAR(150) NOT NULL` | Display name of the route. |
| `stops` | `JSONB NOT NULL`, default `[]` | Ordered array of stop names used for route search. |

The `route_stops_array` constraint requires `stops` to be a JSON array. Example:

```json
["Malappuram", "Ramanattukara", "Kozhikode"]
```

Stop order is significant: the route finder searches in the listed direction and does not infer a reverse-direction service.

### `trip`

One row represents a bus trip operating on a route. The schedule tool filters trips by the first leg's `route_id` and reads the time associated with the actual boarding stop in `stops_list`.

| Column | Type | Meaning |
| --- | --- | --- |
| `trip_id` | `INTEGER` identity, primary key | Trip identifier. |
| `route_id` | `INTEGER NOT NULL` | Foreign key to `route.route_id`. |
| `route_name` | `VARCHAR(150) NOT NULL` | Route name stored with the trip. |
| `bus_name` | `VARCHAR(150) NOT NULL` | Name of the bus/service shown with an available schedule. |
| `stops_list` | `JSONB NOT NULL`, default `[]` | Ordered stop objects with each stop's scheduled time. |

`fk_trip_route` references `route(route_id)` and deletes its trips when that route is deleted. `trip_stops_array` requires `stops_list` to be a JSON array. Example:

```json
[
	{"stop": "Malappuram", "time": "08:00"},
	{"stop": "Ramanattukara", "time": "08:45"},
	{"stop": "Kozhikode", "time": "09:15"}
]
```

Each time is the scheduled time **at that specific stop**. For a passenger boarding at Malappuram, the relevant time is `08:00`, not the later time at Ramanattukara or Kozhikode. The schedule parser accepts valid 24-hour `HH:MM` values. Missing or malformed values are not guessed or generated.

Example SQL to add one route and its trip:

```sql
WITH new_route AS (
		INSERT INTO route (route_name, stops)
		VALUES (
				'Malappuram to Kozhikode',
				'["Malappuram", "Ramanattukara", "Kozhikode"]'::jsonb
		)
		RETURNING route_id, route_name
)
INSERT INTO trip (route_id, route_name, bus_name, stops_list)
SELECT route_id, route_name, 'Coastal Express',
			 '[{"stop":"Malappuram","time":"08:00"},
				 {"stop":"Ramanattukara","time":"08:45"},
				 {"stop":"Kozhikode","time":"09:15"}]'::jsonb
FROM new_route;
```

### `infos`

Stores user feedback received by the complaint tool.

| Column | Type | Meaning |
| --- | --- | --- |
| `info_id` | `INTEGER` identity, primary key | Feedback record identifier. |
| `time` | `TIMESTAMPTZ NOT NULL`, default current timestamp | Time the record was stored. |
| `message` | `TEXT NOT NULL` | Summary with a category prefix. |

The schema has no separate message category column. The tool stores categories in the message text, for example `[COMPLAINT] Bus did not stop at Wandoor`.

### Indexes

Initialization creates indexes on `trip.route_id`, `route.route_name`, `trip.bus_name`, and `infos.time` to support lookups and common access patterns.

## Route and schedule behavior

1. The model extracts the starting place and destination and calls `bus_route_finder`. If the user gave a specific time, it also passes `requested_time` as 24-hour `HH:MM` and sets `requested_time_explicit` to `true`.
2. The existing route service loads `route` rows, resolves place spellings, finds direct routes first, and searches connected routes when needed. It preserves forward direction, prevents route reuse and loops, and limits route-chain depth using `MAX_ROUTE_HOPS`.
3. For each returned route option, the tool uses the first route leg's `route_id` and `from` stop to query `trip`. Stop matching reuses the route finder's exact, alias, and fuzzy matching logic.
4. With an explicit requested time, the tool selects the earliest matching boarding time at or after that time. Without one, it uses the current India-local time from Python's timezone-aware `datetime` and `ZoneInfo("Asia/Kolkata")`.
5. If all daily schedule times have passed, the earliest available time is returned as the next scheduled occurrence tomorrow. The result marks this with `next_day: true`.
6. Only one bus/time is returned for each route option. For a multi-leg route, timing is looked up only for the first leg; no connecting departure is inferred.
7. If the trip query fails, there is no matching trip, or the boarding stop's time is absent or invalid, the route is retained and its schedule status is `unavailable`.

When a schedule is unavailable, the agent should still explain the route and say the schedule time could not be found in the database. It should not invent bus names, stops, times, or connections. Schedule data is not real-time data.

## Other tools

### Complaint and information receiver

The agent classifies feedback as `info`, `complaint`, or `other` and saves an accurate short summary in `infos.message`. After a successful save, it replies: `I have sent it to our team. Thanks for your response.` It must not claim success if saving fails.

### RAG placeholder

`app/tools/rag_tool.py` is currently a placeholder. It does not retrieve documents or provide factual answers.

## Tests

Run the complete test suite from the project root:

```powershell
python -m pytest -q
```

The tests cover route search and schedule lookup, including explicit and current India-local time selection, a single best match among multiple trips, first-leg-only lookup, missing or malformed schedule data, query failures, and the unchanged no-route result. Schedule tests mock PostgreSQL and do not require a live database or Groq API call.

## Model configuration

The OpenAI Python client is configured with Groq's OpenAI-compatible API. The default model is `openai/gpt-oss-20b`; set `GROQ_MODEL` to a model ID enabled for your account if needed. `GROQ_BASE_URL` defaults to `https://api.groq.com/openai/v1`.

## Troubleshooting

- **Missing API key:** set `GROQ_API_KEY` in the root `.env` file.
- **Model not found or unavailable:** check `GROQ_MODEL` against the model IDs enabled for your Groq account.
- **PostgreSQL connection error:** check that PostgreSQL is running and verify the host, port, database name, username, password, and `DATABASE_URL` format.
- **No route found:** verify the stop names and their travel order in `route.stops`. The search follows the stored direction and only uses connected routes when no direct route is found.
- **Route found but no schedule time:** check that `trip.route_id` matches the first leg's route ID and that `stops_list` contains the exact boarding stop with a valid `HH:MM` time.
- **Existing tables do not match:** `init_db.py` creates missing tables but does not alter old table definitions. Back up the database and apply an appropriate migration rather than expecting initialization to change existing columns.
