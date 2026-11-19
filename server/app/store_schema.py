"""The SQLite schema of the server's database; Store runs it on every start, so new tables appear on their own.
Columns added to existing tables go through Store._migrate."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  created REAL NOT NULL,
  taps_total INTEGER NOT NULL DEFAULT 0,
  active_minutes INTEGER NOT NULL DEFAULT 0,
  progress_taps INTEGER NOT NULL DEFAULT 0,
  progress_minutes INTEGER NOT NULL DEFAULT 0,
  boxes INTEGER NOT NULL DEFAULT 0,
  boxes_day TEXT NOT NULL DEFAULT '',
  boxes_today INTEGER NOT NULL DEFAULT 0,
  last_activity REAL NOT NULL DEFAULT 0,
  minute_bucket INTEGER NOT NULL DEFAULT 0,
  minute_taps INTEGER NOT NULL DEFAULT 0,
  minute_counted INTEGER NOT NULL DEFAULT 0,
  since_epic INTEGER NOT NULL DEFAULT 0,
  since_legend INTEGER NOT NULL DEFAULT 0,
  opened_total INTEGER NOT NULL DEFAULT 0,
  frame TEXT,
  badge TEXT,
  shards INTEGER NOT NULL DEFAULT 0,
  loadout TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS players_created ON players (created);
CREATE TABLE IF NOT EXISTS items (
  player_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  first_ts REAL NOT NULL,
  PRIMARY KEY (player_id, item_id)
);
CREATE TABLE IF NOT EXISTS drops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  rarity TEXT NOT NULL,
  is_new INTEGER NOT NULL,
  ts REAL NOT NULL,
  -- Where it came from: 'draw', 'craft' or 'scratch', and for a draw from a limited pool that pool's id. Both empty
  -- on rows from before the columns existed.
  source TEXT NOT NULL DEFAULT '',
  pool TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS drops_player ON drops (player_id, id);
-- A save's draws from one limited pool (app/banners.py): how many, how many since its last featured item, and the
-- shared tiers whose next draw gives a featured item (comma-separated), as the last draw in them gave a standing one.
CREATE TABLE IF NOT EXISTS banner_draws (
  player_id TEXT NOT NULL,
  banner TEXT NOT NULL,
  pity INTEGER NOT NULL DEFAULT 0,
  drawn INTEGER NOT NULL DEFAULT 0,
  guaranteed TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (player_id, banner)
);
CREATE TABLE IF NOT EXISTS activity_budget (
  player_id TEXT PRIMARY KEY,
  balance REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_sessions (
  player_id TEXT NOT NULL,
  session TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  PRIMARY KEY (player_id, session)
);
CREATE TABLE IF NOT EXISTS presets (
  player_id TEXT NOT NULL,
  slot INTEGER NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (player_id, slot)
);
CREATE TABLE IF NOT EXISTS account_links (
  main_user_id TEXT PRIMARY KEY,
  player_id TEXT NOT NULL UNIQUE,
  linked_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_active (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  PRIMARY KEY (day, player_id)
);
CREATE TABLE IF NOT EXISTS guard_days (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  notes TEXT NOT NULL,
  PRIMARY KEY (day, player_id)
);
CREATE TABLE IF NOT EXISTS presence_sessions (
  player_id TEXT NOT NULL,
  session TEXT NOT NULL,
  last_seen REAL NOT NULL,
  PRIMARY KEY (player_id, session)
);
CREATE TABLE IF NOT EXISTS checkins (
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  prize INTEGER NOT NULL,
  shards INTEGER NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY (player_id, day)
);
-- Scratch cards: the prize is decided when a card is bought and paid when it is revealed (revealed = 0 until then).
CREATE TABLE IF NOT EXISTS scratch_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  cells TEXT NOT NULL,
  shards INTEGER NOT NULL,
  item TEXT NOT NULL DEFAULT '',
  ts REAL NOT NULL,
  revealed REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS scratch_cards_player ON scratch_cards (player_id, day);
-- Rock-paper-scissors between saves a (inviter) and b. A row is written when both bets are taken; state goes from
-- 'open' to 'won' (winner holds the save paid `prize`) or 'refunded' exactly once. day: China date of the stakes.
CREATE TABLE IF NOT EXISTS duels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  a TEXT NOT NULL,
  b TEXT NOT NULL,
  bet INTEGER NOT NULL,
  prize INTEGER NOT NULL,
  day TEXT NOT NULL,
  ts REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  winner TEXT NOT NULL DEFAULT '',
  settled REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS duels_a ON duels (a, day);
CREATE INDEX IF NOT EXISTS duels_b ON duels (b, day);
CREATE INDEX IF NOT EXISTS duels_state ON duels (state);
-- Dou dizhu (斗地主) between three saves. A row is written when the three deposits are taken; state goes from 'open'
-- to 'settled' (ddz_seats.delta holds what each seat won or lost, `burnt` the cut kept from the winners) or 'refunded'
-- exactly once. day: China date of the deposits.
CREATE TABLE IF NOT EXISTS ddz_games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  base INTEGER NOT NULL,
  deposit INTEGER NOT NULL,
  day TEXT NOT NULL,
  ts REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  landlord INTEGER NOT NULL DEFAULT -1,
  mult INTEGER NOT NULL DEFAULT 0,
  burnt INTEGER NOT NULL DEFAULT 0,
  settled REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ddz_games_settled ON ddz_games (state, settled);
CREATE TABLE IF NOT EXISTS ddz_seats (
  game_id INTEGER NOT NULL,
  seat INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  delta INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (game_id, seat)
);
CREATE INDEX IF NOT EXISTS ddz_seats_player ON ddz_seats (player_id, day);
-- Shards each save gained (amount > 0) or spent (amount < 0) per China day and source, and how many times.
-- Written in the same transaction as the change; there is no history from before the table existed.
CREATE TABLE IF NOT EXISTS shard_ledger (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id, source)
);
-- One-time data changes already applied to this database.
CREATE TABLE IF NOT EXISTS migrations (
  name TEXT PRIMARY KEY,
  at REAL NOT NULL
);
-- Nickname blocklist as the main site's admin backend sent it (trimmed, not folded).
CREATE TABLE IF NOT EXISTS blocked_words (
  word TEXT PRIMARY KEY
);
-- Single values the operator sets through /admin, as JSON (the notice: minimum version and announcements).
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- Shards the operator gives once to every save that runs `version` or newer, until the reward is ended.
CREATE TABLE IF NOT EXISTS update_rewards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version TEXT NOT NULL,
  shards INTEGER NOT NULL,
  created REAL NOT NULL,
  ended REAL
);
CREATE TABLE IF NOT EXISTS update_reward_claims (
  reward_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  at REAL NOT NULL,
  PRIMARY KEY (reward_id, player_id)
);
-- Rooms once a minute (ts: the minute's start): rooms with members, members, distinct saves among them, the largest
-- room and the listed public rooms. Counts only.
CREATE TABLE IF NOT EXISTS room_samples (
  ts INTEGER PRIMARY KEY,
  rooms INTEGER NOT NULL,
  members INTEGER NOT NULL,
  saves INTEGER NOT NULL,
  largest INTEGER NOT NULL,
  public INTEGER NOT NULL
);
-- Rooms as the server left them when it stopped (see RoomManager.snapshot); read back and emptied at the next start.
-- host: the host's save; banned: JSON list of the saves the host removed.
CREATE TABLE IF NOT EXISTS room_restore (
  room TEXT PRIMARY KEY,
  public INTEGER NOT NULL,
  host TEXT,
  banned TEXT NOT NULL,
  saved REAL NOT NULL
);
-- Server-wide counts per China day (room joins, pokes, profile views, emotes, duel invites, cheer rounds).
CREATE TABLE IF NOT EXISTS daily_counts (
  day TEXT NOT NULL,
  key TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, key)
);
-- Per save and China day: reported taps that were not credited, cooldowns the server started for input too fast
-- for a hand, cooldowns the client's own guard started, cooldowns for input at one steady rate (a rule the guard
-- replaced; kept for the days it ran), times the guard began to count the save's input as automatic, and taps
-- the client said other software sent.
CREATE TABLE IF NOT EXISTS tap_flags (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  dropped INTEGER NOT NULL DEFAULT 0,
  server_cooldowns INTEGER NOT NULL DEFAULT 0,
  client_cooldowns INTEGER NOT NULL DEFAULT 0,
  steady INTEGER NOT NULL DEFAULT 0,
  auto INTEGER NOT NULL DEFAULT 0,
  injected INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id)
);
-- Saves whose taps earn nothing until the operator releases them, with who held them and why.
CREATE TABLE IF NOT EXISTS tap_holds (
  player_id TEXT PRIMARY KEY,
  since REAL NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT ''
);
-- What the operator changed through /admin: who (the main site's admin), on which save, what (JSON) and why.
CREATE TABLE IF NOT EXISTS admin_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS admin_log_player ON admin_log (player_id, id);
-- Park coins each save gained (amount > 0) or spent (amount < 0) per China day and source, like shard_ledger.
CREATE TABLE IF NOT EXISTS coin_ledger (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id, source)
);
-- A save's own coin history (GET /api/park/ledger).
CREATE INDEX IF NOT EXISTS coin_ledger_player ON coin_ledger (player_id, day);
-- Shared park amounts, such as the lottery pool and its second-prize rollover, written in the caller's transaction.
CREATE TABLE IF NOT EXISTS park_counters (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0
);
-- Park wins every running pet hears of (status `park.news`); kept PARK_NEWS_DAYS.
CREATE TABLE IF NOT EXISTS park_news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  nick TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '{}'
);
-- park: scratch tables
-- Coin scratch cards (park_scratch.py), decided when bought and paid when revealed (revealed = 0 until then). tier:
-- again, shards, emote, skin, big or miss; shards, coins and item are what the reveal pays. A save's first card of
-- each kind is never pruned: it marks the first-card prize as given.
CREATE TABLE IF NOT EXISTS park_scratch_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  kind TEXT NOT NULL,
  cells TEXT NOT NULL,
  tier TEXT NOT NULL,
  shards INTEGER NOT NULL DEFAULT 0,
  coins INTEGER NOT NULL DEFAULT 0,
  item TEXT NOT NULL DEFAULT '',
  ts REAL NOT NULL,
  revealed REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS park_scratch_cards_player ON park_scratch_cards (player_id, revealed);
-- park: race tables
-- Dumpling races (park_race.py), id = when its bets open (unix seconds). seed (hex), ranking and result stay
-- server-side until status 'running'; result ({start, order, rolls, moves, rest}) is kept for good, for replays
-- (servers before 1.2.4 cleared it after two days, leaving ''). step_ms and slow_ms: playback step lengths before and
-- in the last round.
-- status: open (prepared or taking bets), running, settled, void (called off, bets refunded).
CREATE TABLE IF NOT EXISTS park_races (
  id INTEGER PRIMARY KEY,
  starts_at REAL NOT NULL,
  ends_at REAL NOT NULL,
  step_ms INTEGER NOT NULL,
  slow_ms INTEGER NOT NULL,
  seed TEXT NOT NULL,
  hash TEXT NOT NULL,
  setup TEXT NOT NULL,
  ranking TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS park_races_status ON park_races (status, id);
-- Bets on a race, one row per bet with the odds it was placed at (tenths); prize once settled, in tenths of a coin
-- (coins × odds; 0 for a losing bet).
CREATE TABLE IF NOT EXISTS park_race_bets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  race_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  member TEXT NOT NULL,
  coins INTEGER NOT NULL,
  odds INTEGER NOT NULL,
  prize INTEGER NOT NULL DEFAULT 0,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS park_race_bets_race ON park_race_bets (race_id, player_id);
-- park: lottery tables
-- The daily lottery (lottery.py): one row per China day, made before the day's first ticket. `hash` is SHA-256 of
-- number + salt and is public all day; number and salt go public once `drawn` is set. `result` is the draw's JSON.
CREATE TABLE IF NOT EXISTS lottery_days (
  day TEXT PRIMARY KEY,
  number TEXT NOT NULL,
  salt TEXT NOT NULL,
  hash TEXT NOT NULL,
  created REAL NOT NULL,
  drawn REAL,
  result TEXT NOT NULL DEFAULT '{}'
);
-- One row per ticket; `tier` (1 top, 2 second, 3 third, 0 none) and `prize` are set by the draw.
CREATE TABLE IF NOT EXISTS lottery_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  number TEXT NOT NULL,
  ts REAL NOT NULL,
  tier INTEGER NOT NULL DEFAULT 0,
  prize INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS lottery_tickets_day ON lottery_tickets (day, player_id);
-- A save's own days (lottery_history), without scanning every ticket of the server.
CREATE INDEX IF NOT EXISTS lottery_tickets_player ON lottery_tickets (player_id, day);
-- park: redeem tables
-- Redeem codes made through /admin/codes (see redeem.py). code: normalized (upper case, no dashes or spaces); custom: an
-- admin wrote it rather than the generator; uses: claims allowed, used: claims so far; expires: Unix seconds, 0 never.
CREATE TABLE IF NOT EXISTS redeem_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  custom INTEGER NOT NULL DEFAULT 0,
  shards INTEGER NOT NULL DEFAULT 0,
  coins INTEGER NOT NULL DEFAULT 0,
  uses INTEGER NOT NULL DEFAULT 1,
  used INTEGER NOT NULL DEFAULT 0,
  expires REAL NOT NULL DEFAULT 0,
  disabled REAL,
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL
);
-- One row per code a save redeemed; a save redeems each code once.
CREATE TABLE IF NOT EXISTS redeem_claims (
  code_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY (code_id, player_id)
);
CREATE INDEX IF NOT EXISTS redeem_claims_player ON redeem_claims (player_id);
-- Wrong codes a save entered lately (older rows go when it enters the next), and the save's lockout: locked until
-- [until], [locks] lockouts so far, the last at [last].
CREATE TABLE IF NOT EXISTS redeem_tries (
  player_id TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS redeem_tries_player ON redeem_tries (player_id, ts);
CREATE TABLE IF NOT EXISTS redeem_locks (
  player_id TEXT PRIMARY KEY,
  until REAL NOT NULL,
  locks INTEGER NOT NULL DEFAULT 0,
  last REAL NOT NULL
);
"""
