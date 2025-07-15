from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import sqlite3
import bot.database as db
db.init_db()
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def index():
    conn = sqlite3.connect("../musicbot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM stats ORDER BY played_at DESC LIMIT 10")
    stats = c.fetchall()
    conn.close()
    html = "<h1>Recent Songs Played</h1><ul>"
    for stat in stats:
        html += f"<li>{stat[2]} by user {stat[1]} at {stat[3]}</li>"
    html += "</ul>"
    return html

@app.get("/analytics/songs", response_class=JSONResponse)
async def top_songs():
    data = db.get_song_play_counts(10)
    return {"labels": [row[0] for row in data], "counts": [row[1] for row in data]}

@app.get("/analytics/servers", response_class=JSONResponse)
async def top_servers():
    data = db.get_guild_stats()
    # Use guild_name for labels
    return {"labels": [row[1] for row in data], "counts": [row[2] for row in data]}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    # Top songs
    song_data = db.get_song_play_counts(10)
    # Top servers
    server_data = db.get_guild_stats()
    html = """
    <html>
    <head>
        <title>Music Bot Analytics</title>
        <script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
    </head>
    <body>
        <h1>Music Bot Analytics</h1>
        <h2>Top Played Songs</h2>
        <canvas id='songsChart' width='400' height='200'></canvas>
        <div id='noSongsMsg'></div>
        <h2>Top Servers by Play Count</h2>
        <canvas id='serversChart' width='400' height='200'></canvas>
        <div id='noServersMsg'></div>
        <script>
        const songLabels = """ + str([row[0] for row in song_data]) + """;
        const songCounts = """ + str([row[1] for row in song_data]) + """;
        // Use guild_name for labels
        const serverLabels = """ + str([row[1] for row in server_data]) + """;
        const serverCounts = """ + str([row[2] for row in server_data]) + """;
        if (songLabels.length === 0) {
            document.getElementById('noSongsMsg').innerText = 'No song data available yet.';
        } else {
            new Chart(document.getElementById('songsChart'), {
                type: 'bar',
                data: { labels: songLabels, datasets: [{ label: 'Play Count', data: songCounts }] },
            });
        }
        if (serverLabels.length === 0) {
            document.getElementById('noServersMsg').innerText = 'No server data available yet.';
        } else {
            new Chart(document.getElementById('serversChart'), {
                type: 'bar',
                data: { labels: serverLabels, datasets: [{ label: 'Play Count', data: serverCounts }] },
            });
        }
        </script>
    </body>
    </html>
    """
    return html 