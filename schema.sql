-- users
CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  referrer_id BIGINT NULL,
  verified BOOLEAN NOT NULL DEFAULT FALSE,
  verified_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- channels
CREATE TABLE IF NOT EXISTS channels (
  id BIGSERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- referrals
CREATE TABLE IF NOT EXISTS referrals (
  invited_user_id BIGINT PRIMARY KEY,
  referrer_id BIGINT NOT NULL,
  credited BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_referrals_invited ON referrals(invited_user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_credited_referrer ON referrals(referrer_id, credited);

-- settings
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- admins
CREATE TABLE IF NOT EXISTS admins (
  user_id BIGINT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- prizes
CREATE TABLE IF NOT EXISTS prizes (
  id BIGSERIAL PRIMARY KEY,
  place INT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prizes_place ON prizes(place);
