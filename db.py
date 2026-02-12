import asyncpg
from typing import List, Optional, Tuple, Dict, Any

from config import DATABASE_URL, ENV_ADMIN_IDS


_pool: Optional[asyncpg.Pool] = None


# =========================
# Connection / Init
# =========================
async def db_connect() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _pool


async def db_close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def db_init() -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # ---- schema ----
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
              user_id BIGINT PRIMARY KEY,
              username TEXT,
              first_name TEXT,
              referrer_id BIGINT NULL,
              verified BOOLEAN NOT NULL DEFAULT FALSE,
              verified_at TIMESTAMPTZ NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
              id BIGSERIAL PRIMARY KEY,
              username TEXT UNIQUE NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
              invited_user_id BIGINT PRIMARY KEY,
              referrer_id BIGINT NOT NULL,
              credited BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)
            await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_referrals_invited ON referrals(invited_user_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_credited_referrer ON referrals(referrer_id, credited);")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
              user_id BIGINT PRIMARY KEY,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS prizes (
              id BIGSERIAL PRIMARY KEY,
              place INT NOT NULL,
              title TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_prizes_place ON prizes(place);")

            # ---- defaults ----
            await conn.execute("""
            INSERT INTO settings(key, value) VALUES
              ('contest_active','1'),
              ('ad_footer',''),
              ('ad_btn_text',''),
              ('ad_btn_url','')
            ON CONFLICT (key) DO NOTHING;
            """)

            # ---- env admins ----
            for aid in ENV_ADMIN_IDS:
                await conn.execute(
                    "INSERT INTO admins(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
                    int(aid),
                )


# =========================
# Admin stats
# =========================
async def admin_stats() -> Dict[str, Any]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        users_total = int(await conn.fetchval("SELECT COUNT(*) FROM users"))
        users_verified = int(await conn.fetchval("SELECT COUNT(*) FROM users WHERE verified=TRUE"))
        users_not_verified = int(await conn.fetchval("SELECT COUNT(*) FROM users WHERE verified=FALSE"))

        ref_total = int(await conn.fetchval("SELECT COUNT(*) FROM referrals"))
        ref_credited = int(await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE credited=TRUE"))
        ref_not_credited = int(await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE credited=FALSE"))

        today_users = int(await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE"))
        today_referrals = int(await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE created_at::date = CURRENT_DATE"))

        today_verified_created = int(await conn.fetchval("""
            SELECT COUNT(*) FROM users
            WHERE verified=TRUE AND created_at::date = CURRENT_DATE
        """))

        prizes_count = int(await conn.fetchval("SELECT COUNT(*) FROM prizes"))
        channels_count = int(await conn.fetchval("SELECT COUNT(*) FROM channels"))

        contest_active = (await get_setting("contest_active", "1")) == "1"

        return {
            "users_total": users_total,
            "users_verified": users_verified,
            "users_not_verified": users_not_verified,
            "ref_total": ref_total,
            "ref_credited": ref_credited,
            "ref_not_credited": ref_not_credited,
            "today_users": today_users,
            "today_referrals": today_referrals,
            "today_verified_created": today_verified_created,
            "prizes_count": prizes_count,
            "channels_count": channels_count,
            "contest_active": contest_active,
        }


async def top_referrers(limit: int = 10) -> List[asyncpg.Record]:
    return await get_top(limit)


async def get_top1_score() -> int:
    pool = await db_connect()
    async with pool.acquire() as conn:
        mx = await conn.fetchval("""
            SELECT COALESCE(MAX(score), 0) AS mx
            FROM (
                SELECT u.user_id,
                       COUNT(r.invited_user_id) AS score
                FROM users u
                LEFT JOIN referrals r
                  ON r.referrer_id = u.user_id AND r.credited = TRUE
                GROUP BY u.user_id
            ) t
        """)
        return int(mx or 0)


# =========================
# Settings
# =========================
async def set_setting(key: str, value: str) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings(key, value)
            VALUES($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)


async def get_setting(key: str, default: str = "") -> str:
    pool = await db_connect()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key=$1", key)
        return str(row["value"]) if row else default


async def fix_referrals_duplicates() -> None:
    # Postgres’da invited_user_id PRIMARY KEY bo‘lgani uchun amalda duplicate bo‘lmaydi.
    # Lekin eski DB’dan migrate qilganda ehtiyot uchun qoldirdim.
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM referrals r
            USING referrals r2
            WHERE r.invited_user_id = r2.invited_user_id
              AND r.ctid < r2.ctid
        """)


async def is_contest_active() -> bool:
    return (await get_setting("contest_active", "1")) == "1"


async def contest_end() -> None:
    await set_setting("contest_active", "0")


async def contest_start() -> None:
    await set_setting("contest_active", "1")


# =========================
# Users / Admins
# =========================
async def count_users() -> int:
    pool = await db_connect()
    async with pool.acquire() as conn:
        return int(await conn.fetchval("SELECT COUNT(*) FROM users"))


async def is_admin_db(user_id: int) -> bool:
    pool = await db_connect()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM admins WHERE user_id=$1", int(user_id))
        return row is not None


async def admin_add(user_id: int) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO admins(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
            int(user_id),
        )


async def admin_del(user_id: int) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id=$1", int(user_id))


async def admin_list() -> List[int]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM admins ORDER BY created_at ASC")
        return [int(r["user_id"]) for r in rows]


async def upsert_user(user_id: int, username: str, first_name: str, referrer_id: Optional[int]) -> None:
    if referrer_id == user_id:
        referrer_id = None

    pool = await db_connect()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT referrer_id FROM users WHERE user_id=$1", int(user_id))

            if row is None:
                await conn.execute("""
                    INSERT INTO users(user_id, username, first_name, referrer_id, verified)
                    VALUES($1, $2, $3, $4, FALSE)
                """, int(user_id), username, first_name, referrer_id)
                return

            existing_ref = row["referrer_id"]
            if existing_ref is None and referrer_id is not None:
                await conn.execute("""
                    UPDATE users
                    SET referrer_id=$1, username=$2, first_name=$3
                    WHERE user_id=$4
                """, referrer_id, username, first_name, int(user_id))
            else:
                await conn.execute("""
                    UPDATE users
                    SET username=$1, first_name=$2
                    WHERE user_id=$3
                """, username, first_name, int(user_id))


async def set_verified(user_id: int, verified: bool) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        if verified:
            await conn.execute("""
                UPDATE users
                SET verified=TRUE, verified_at=NOW()
                WHERE user_id=$1
            """, int(user_id))
        else:
            await conn.execute("""
                UPDATE users
                SET verified=FALSE, verified_at=NULL
                WHERE user_id=$1
            """, int(user_id))


async def is_verified(user_id: int) -> bool:
    pool = await db_connect()
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT verified FROM users WHERE user_id=$1", int(user_id))
        return bool(v) if v is not None else False


async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", int(user_id))


async def get_all_user_ids() -> List[int]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [int(r["user_id"]) for r in rows]


# =========================
# Referrals / Scoring
# =========================
async def ensure_referral(invited_user_id: int, referrer_id: int) -> None:
    if invited_user_id == referrer_id:
        return
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO referrals(invited_user_id, referrer_id, credited)
            VALUES($1, $2, FALSE)
            ON CONFLICT (invited_user_id) DO NOTHING
        """, int(invited_user_id), int(referrer_id))


async def credit_referrer_if_needed(invited_user_id: int) -> Optional[int]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        async with conn.transaction():
            verified = await conn.fetchval(
                "SELECT verified FROM users WHERE user_id=$1",
                int(invited_user_id),
            )
            if not verified:
                return None

            r = await conn.fetchrow("""
                SELECT referrer_id, credited
                FROM referrals
                WHERE invited_user_id=$1
                FOR UPDATE
            """, int(invited_user_id))
            if not r or bool(r["credited"]) is True:
                return None

            referrer_id = int(r["referrer_id"])
            await conn.execute(
                "UPDATE referrals SET credited=TRUE WHERE invited_user_id=$1",
                int(invited_user_id),
            )
            return referrer_id


async def get_stats_for_user(user_id: int) -> Tuple[int, int, int]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
              COUNT(*)::int AS total,
              COALESCE(SUM(CASE WHEN credited=TRUE THEN 1 ELSE 0 END), 0)::int AS real
            FROM referrals
            WHERE referrer_id=$1
        """, int(user_id))
        total = int(row["total"] or 0)
        real = int(row["real"] or 0)
        return total, real, real


async def get_top(limit: int = 10) -> List[asyncpg.Record]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.user_id, u.first_name, u.username,
                   COUNT(r.invited_user_id)::int AS score
            FROM users u
            LEFT JOIN referrals r
              ON r.referrer_id = u.user_id AND r.credited = TRUE
            GROUP BY u.user_id
            ORDER BY score DESC, u.created_at ASC
            LIMIT $1
        """, int(limit))


async def get_rank(user_id: int) -> Optional[int]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            WITH scores AS (
                SELECT u.user_id AS uid,
                       COUNT(r.invited_user_id)::int AS score
                FROM users u
                LEFT JOIN referrals r
                  ON r.referrer_id = u.user_id AND r.credited = TRUE
                GROUP BY u.user_id
            ),
            ranked AS (
                SELECT uid,
                       score,
                       DENSE_RANK() OVER (ORDER BY score DESC) AS rnk
                FROM scores
            )
            SELECT rnk FROM ranked WHERE uid=$1
        """, int(user_id))
        return int(row["rnk"]) if row else None


# =========================
# Prizes
# =========================
async def prize_add(place: int, title: str, description: str = "") -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO prizes(place, title, description)
            VALUES($1, $2, $3)
        """, int(place), title.strip(), description.strip())


async def prize_del(prize_id: int) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM prizes WHERE id=$1", int(prize_id))


async def prize_list() -> List[asyncpg.Record]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM prizes ORDER BY place ASC, id ASC")


# =========================
# TZ: Konkursni tugatish + Umumiy tozalash
# =========================
async def _keep_only_env_admins(conn: asyncpg.Connection) -> None:
    if ENV_ADMIN_IDS:
        ids = [int(x) for x in ENV_ADMIN_IDS]
        await conn.execute(
            "DELETE FROM admins WHERE NOT (user_id = ANY($1::bigint[]))",
            ids,
        )
    else:
        await conn.execute("DELETE FROM admins")

async def reset_all_data(
    *,
    delete_users: bool = True,
    delete_referrals: bool = True,
    delete_prizes: bool = False,
    delete_admins: bool = False,
    keep_env_admins: bool = True,
    reset_settings: bool = False,
) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if delete_referrals:
                await conn.execute("TRUNCATE TABLE referrals")

            if delete_users:
                await conn.execute("TRUNCATE TABLE users")

            if delete_prizes:
                await conn.execute("TRUNCATE TABLE prizes RESTART IDENTITY")

            if delete_admins:
                if keep_env_admins:
                    await _keep_only_env_admins(conn)
                else:
                    await conn.execute("TRUNCATE TABLE admins")

            if reset_settings:
                await conn.execute("TRUNCATE TABLE settings")
                await conn.execute("""
                    INSERT INTO settings(key, value) VALUES
                      ('contest_active','1'),
                      ('ad_footer',''),
                      ('ad_btn_text',''),
                      ('ad_btn_url','')
                    ON CONFLICT (key) DO NOTHING;
                """)


async def contest_finish_and_clear_users(
    *,
    clear_prizes: bool = False,
    clear_admins: bool = False,
    keep_env_admins: bool = True,
) -> None:
    await contest_end()
    await reset_all_data(
        delete_users=True,
        delete_referrals=True,
        delete_prizes=clear_prizes,
        delete_admins=clear_admins,
        keep_env_admins=keep_env_admins,
        reset_settings=False,
    )


# -------- channels --------
async def channel_add(username: str) -> None:
    username = username.strip()
    if not username:
        return
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO channels(username)
            VALUES($1)
            ON CONFLICT (username) DO NOTHING
        """, username)


async def channel_del(username: str) -> None:
    pool = await db_connect()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM channels WHERE username=$1", username.strip())


async def channel_list() -> List[str]:
    pool = await db_connect()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT username FROM channels ORDER BY id ASC")
        return [str(r["username"]) for r in rows]
