import sqlite3

def get_db():
    conn = sqlite3.connect("musicbot.db")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        song TEXT,
        song_url TEXT,
        duration INTEGER,
        guild_id TEXT,
        guild_name TEXT,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

# Insert a playback record
def insert_playback(user_id, song, song_url, duration, guild_id, guild_name):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO stats (user_id, song, song_url, duration, guild_id, guild_name) VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, song, song_url, duration, guild_id, guild_name))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB insert_playback error: {e}")

# Get recent playbacks
def get_recent_playbacks(limit=10):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''SELECT * FROM stats ORDER BY played_at DESC LIMIT ?''', (limit,))
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"DB get_recent_playbacks error: {e}")
        return []

# Get song play counts for analytics (top N songs)
def get_song_play_counts(limit=10):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''SELECT song, COUNT(*) as play_count FROM stats GROUP BY song ORDER BY play_count DESC LIMIT ?''', (limit,))
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"DB get_song_play_counts error: {e}")
        return []

# Get server (guild) stats
def get_guild_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''SELECT guild_id, guild_name, COUNT(*) as play_count FROM stats GROUP BY guild_id, guild_name ORDER BY play_count DESC''')
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"DB get_guild_stats error: {e}")
        return [] 