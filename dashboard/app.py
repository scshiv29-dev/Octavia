from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import sqlite3

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