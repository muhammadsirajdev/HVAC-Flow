-- App schema (idempotent). Applied by `python -m backend.db.init_db`.
-- Move to Alembic migrations once the schema settles.
-- The knowledge base is NOT here: it lives in Chroma (see backend/rag).

CREATE TABLE IF NOT EXISTS customers (
  customer_id  BIGSERIAL PRIMARY KEY,
  name         TEXT,
  email        TEXT,
  phone        TEXT,                     -- E.164, e.g. +17867976193
  address      TEXT,
  opted_out    BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS customers_email_uq ON customers (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS customers_phone_uq ON customers (phone) WHERE phone IS NOT NULL;

DO $$ BEGIN
  CREATE TYPE case_status AS ENUM ('open','booked','done','closed','cancelled','needs_person');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS cases (
  case_id          BIGSERIAL PRIMARY KEY,
  customer_id      BIGINT NOT NULL REFERENCES customers,
  status           case_status NOT NULL DEFAULT 'open',
  channel          TEXT NOT NULL,                -- web | email | whatsapp
  email_thread_id  TEXT UNIQUE,
  wa_last_inbound  TIMESTAMPTZ,
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at        TIMESTAMPTZ
);
-- one open case per customer
CREATE UNIQUE INDEX IF NOT EXISTS cases_one_open ON cases (customer_id)
  WHERE status IN ('open','booked','needs_person');

CREATE TABLE IF NOT EXISTS case_events (
  event_id    BIGSERIAL PRIMARY KEY,
  case_id     BIGINT NOT NULL REFERENCES cases,
  from_status case_status,
  to_status   case_status NOT NULL,
  reason      TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS slots (
  slot_id    BIGSERIAL PRIMARY KEY,
  starts_at  TIMESTAMPTZ NOT NULL UNIQUE,
  ends_at    TIMESTAMPTZ NOT NULL,
  technician TEXT,
  taken      BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS bookings (
  booking_id  BIGSERIAL PRIMARY KEY,
  case_id     BIGINT NOT NULL REFERENCES cases,
  slot_id     BIGINT NOT NULL REFERENCES slots,
  service     TEXT NOT NULL,
  address     TEXT NOT NULL,
  problem     TEXT,
  technician  TEXT,
  reminded    BOOLEAN NOT NULL DEFAULT false,
  active      BOOLEAN NOT NULL DEFAULT true,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Notification status: a booking whose confirmation/Slack post never went out (crash, outage)
-- is detected and sent later instead of being lost.
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS confirmation_sent_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS slack_posted_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_per_slot ON bookings (slot_id) WHERE active;
CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_per_case ON bookings (case_id) WHERE active;

CREATE TABLE IF NOT EXISTS messages (
  message_id       BIGSERIAL PRIMARY KEY,
  case_id          BIGINT REFERENCES cases,
  channel          TEXT NOT NULL,
  direction        TEXT NOT NULL,              -- in | out
  thread_key       TEXT,                       -- chat session id / email thread / phone
  provider_msg_id  TEXT,
  body             TEXT,
  meta             JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS messages_provider_uq ON messages (channel, provider_msg_id)
  WHERE provider_msg_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS slack_events (
  event_id    TEXT PRIMARY KEY,
  case_id     BIGINT,
  command     TEXT,
  handled_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
