import discord
from discord.ext import commands
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import os
from dotenv import load_dotenv
import logging
import functools
from .music_queue import MusicQueue
import asyncio
import time
import bot.database as db

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('musicbot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("musicbot")

# Load environment variables from .env
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Helper for yt-dlp extraction in a thread
async def extract_info_async(loop, query, ydl_opts):
    def ytdlp_extract(query, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)
    return await loop.run_in_executor(None, functools.partial(ytdlp_extract, query, ydl_opts))

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = MusicQueue()
        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
        logger.info("Music cog initialized.")
        self.resolver_tasks = {}  # guild_id: asyncio.Task
        self.song_start_times = {}  # guild_id: (start_time, retries, url, title, ctx, duration, requester, search_query)
        self.disconnect_timers = {}  # guild_id: asyncio.Task
        self.last_text_channel = {}  # guild_id: ctx.channel

    @commands.command()
    async def play(self, ctx, *, query):
        logger.info(f"!play called by {ctx.author} in guild {ctx.guild.id} with query: {query}")
        if ctx.author.voice is None:
            await ctx.send("You are not in a voice channel.")
            logger.warning(f"User {ctx.author} tried to play without being in a voice channel.")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect(self_mute=True, self_deaf=True)
        vc = ctx.voice_client
        loop = ctx.bot.loop

        # Handle Spotify playlist links
        spotify_playlist_regex = re.compile(r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)")
        playlist_match = spotify_playlist_regex.search(query)
        if playlist_match:
            playlist_id = playlist_match.group(1)
            playlist = self.sp.playlist(playlist_id)
            tracks = playlist['tracks']['items']
            added = 0
            # Play first track immediately
            for idx, item in enumerate(tracks):
                track = item['track']
                if not track: continue
                track_query = f"{track['name']} {track['artists'][0]['name']}"
                if idx == 0:
                    # Resolve and play first track
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'quiet': True,
                        'default_search': 'ytsearch',
                        'noplaylist': False,
                        'extract_flat': False,
                        'socket_timeout': 30,
                    }
                    try:
                        info = await extract_info_async(loop, track_query, ydl_opts)
                        if 'entries' in info:
                            info = info['entries'][0]
                        url2 = info['url']
                        title = info.get('title', 'Unknown Title')
                        duration = info.get('duration', 0)
                        if vc.is_playing() or not self.queue.is_empty():
                            self.queue.add(ctx.guild.id, url2, title, ctx, duration, ctx.author.display_name)
                            await ctx.send(f"Queued: {title}")
                        else:
                            self.queue.set_now_playing(ctx.guild.id, url2, title, ctx, duration, ctx.author.display_name)
                            await self.play_next(ctx)
                            await ctx.send(f"Now playing: {title}")
                        added += 1
                        logger.info(f"Added and played first track from Spotify playlist: {title} (requested by {ctx.author})")
                    except Exception as e:
                        logger.error(f"Failed to add first track from Spotify playlist: {track_query} - {e}")
                else:
                    # Add as pending
                    self.queue.add(ctx.guild.id, track_query, None, ctx, None, ctx.author.display_name, pending=True)
                    added += 1
            await ctx.send(f"Added Spotify playlist: {playlist['name']} with {added} tracks to the queue.")
            # Start background resolver if not running
            if ctx.guild.id not in self.resolver_tasks or self.resolver_tasks[ctx.guild.id].done():
                self.resolver_tasks[ctx.guild.id] = asyncio.create_task(self.resolve_pending(ctx.guild.id, ctx))
            return

        # Handle Spotify single track links
        spotify_regex = re.compile(r"open\.spotify\.com/track/([a-zA-Z0-9]+)")
        match = spotify_regex.search(query)
        if match:
            track_id = match.group(1)
            track = self.sp.track(track_id)
            query = f"{track['name']} {track['artists'][0]['name']}"

        # Detect YouTube playlist
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'default_search': 'ytsearch',
            'noplaylist': False,
            'extract_flat': False,
            'socket_timeout': 30,
        }

        # --- NEW: Check if song is already in the queue ---
        tracks = self.queue.get_queue(ctx.guild.id)
        found = False
        for idx, (url, title, ctx_obj, duration, requester, search_query) in enumerate(tracks):
            match_title = (title and query.lower() in title.lower())
            match_url = (url and query.lower() in url.lower())
            match_search = (search_query and query.lower() in search_query.lower())
            if match_title or match_url or match_search:
                found = True
                mins, secs = divmod(duration or 0, 60)
                eta = sum(t[3] or 0 for t in tracks[:idx])
                eta_m, eta_s = divmod(eta, 60)
                display_title = title or search_query or url or "(resolving...)"
                await ctx.send(
                    f"'{display_title}' is already in the queue at position {idx+1}. ETA: {eta_m:02}:{eta_s:02} (Length: {mins:02}:{secs:02})"
                )
                logger.info(f"Play: {display_title} already in queue for {ctx.author} at position {idx+1} ETA {eta_m:02}:{eta_s:02}")
                return
        # --- END NEW ---

        try:
            info = await extract_info_async(loop, query, ydl_opts)
            if 'entries' in info:
                # Playlist detected
                entries = info['entries']
                for entry in entries:
                    url2 = entry['url']
                    title = entry.get('title', 'Unknown Title')
                    duration = entry.get('duration', 0)
                    self.queue.add(ctx.guild.id, url2, title, ctx, duration, ctx.author.display_name)
                    logger.info(f"Added track from YouTube playlist: {title} (requested by {ctx.author})")
                await ctx.send(f"Added playlist: {info.get('title', 'Playlist')} with {len(entries)} tracks to the queue.")
                if not vc.is_playing() and not self.queue.is_empty():
                    await self.play_next(ctx)
                return
            else:
                url2 = info['url']
                title = info.get('title', 'Unknown Title')
                duration = info.get('duration', 0)
        except Exception as e:
            logger.error(f"Failed to extract info for query '{query}': {e}")
            await ctx.send("Failed to process your request.")
            return

        # Add to queue or play immediately
        if vc.is_playing() or not self.queue.is_empty():
            self.queue.add(ctx.guild.id, url2, title, ctx, duration, ctx.author.display_name)
            await ctx.send(f"Queued: {title}")
            logger.info(f"Queued: {title} (requested by {ctx.author})")
        else:
            self.queue.set_now_playing(ctx.guild.id, url2, title, ctx, duration, ctx.author.display_name)
            await self.play_next(ctx)
            logger.info(f"Now playing: {title} (requested by {ctx.author})")

    async def play_next(self, ctx, retry_data=None):
        vc = ctx.voice_client
        if retry_data:
            url2, title, ctx_obj, duration, requester, search_query, retries = retry_data
        else:
            next_track = self.queue.next(ctx.guild.id)
            if not next_track:
                await ctx.send("Queue ended.")
                logger.info("Queue ended.")
                # Start disconnect timer
                if ctx.guild.id in self.disconnect_timers:
                    self.disconnect_timers[ctx.guild.id].cancel()
                self.disconnect_timers[ctx.guild.id] = asyncio.create_task(self.disconnect_after_timeout(ctx.guild.id))
                return
            url2, title, ctx_obj, duration, requester, search_query = next_track
            retries = 0
        # Cancel disconnect timer if a new song starts
        if ctx.guild.id in self.disconnect_timers:
            self.disconnect_timers[ctx.guild.id].cancel()
        def after_playback(error=None):
            elapsed = time.time() - self.song_start_times.get(ctx.guild.id, (0,))[0]
            if error:
                logger.error(f"FFmpeg error: {error}")
            if elapsed < 30 and retries < 2:
                logger.warning(f"Song '{title or search_query}' stopped early after {elapsed:.2f}s, retrying ({retries+1}/2)...")
                coro = self.play_next(ctx, retry_data=(url2, title, ctx_obj, duration, requester, search_query, retries+1))
                asyncio.run_coroutine_threadsafe(coro, ctx.bot.loop)
            else:
                coro = self.play_next(ctx)
                asyncio.run_coroutine_threadsafe(coro, ctx.bot.loop)
                if elapsed < 30:
                    asyncio.run_coroutine_threadsafe(ctx.send(f"Failed to play '{title or search_query}' after 2 retries, skipping."), ctx.bot.loop)
        self.song_start_times[ctx.guild.id] = (time.time(), retries, url2, title, ctx_obj, duration, requester, search_query)
        self.last_text_channel[ctx.guild.id] = ctx.channel
        # --- Insert playback record ---
        user_id = getattr(ctx.author, 'id', str(ctx.author))
        guild_id = str(ctx.guild.id)
        guild_name = str(ctx.guild.name)
        db.insert_playback(user_id, title or search_query or url2, url2, duration, guild_id, guild_name)
        # --- End insert ---
        vc.play(discord.FFmpegPCMAudio(url2), after=after_playback)
        await ctx.send(f"Now playing: {title or search_query}")
        logger.info(f"Now playing: {title or search_query} (requested by {requester})")

    async def disconnect_after_timeout(self, guild_id):
        await asyncio.sleep(300)  # 5 minutes
        # Check if still not playing
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and not guild.voice_client.is_playing():
            channel = self.last_text_channel.get(guild_id)
            await guild.voice_client.disconnect()
            if channel:
                await channel.send("No songs played for 5 minutes. Disconnected from voice.")
            logger.info(f"Disconnected from voice in guild {guild_id} after 5 minutes of inactivity.")

    @commands.command(name="queue")
    async def queue_(self, ctx, page: int = 1):
        tracks = self.queue.get_queue(ctx.guild.id)
        if not tracks:
            await ctx.send("Queue is empty.")
            logger.info(f"Queue checked by {ctx.author} - empty.")
            return
        per_page = 10
        pages = (len(tracks) + per_page - 1) // per_page
        page = max(1, min(page, pages))
        start = (page - 1) * per_page
        end = start + per_page
        embed = discord.Embed(title=f"Queue (Page {page}/{pages})", color=discord.Color.blue())
        now_playing = self.queue.get_now_playing(ctx.guild.id)
        elapsed = 0
        if now_playing and now_playing[3]:
            elapsed = now_playing[3]
        for i, (url, title, ctx_obj, duration, requester, search_query) in enumerate(tracks[start:end], start=start+1):
            if title is None or duration is None:
                display_title = search_query or url or "(resolving...)"
                display_time = "(resolving...)"
                est_time = "(resolving...)"
            else:
                display_title = title
                mins, secs = divmod(duration, 60)
                display_time = f"{mins:02}:{secs:02}"
                prev_tracks = tracks[:i-1]
                est_seconds = sum(t[3] for t in prev_tracks if t[3])
                est_time = f"{est_seconds//60:02}:{est_seconds%60:02}"
            embed.add_field(
                name=f"{i}. {display_title}",
                value=f"Requested by: {requester} | Length: {display_time} | ETA: {est_time}",
                inline=False
            )
        await ctx.send(embed=embed)
        logger.info(f"Queue page {page} sent to {ctx.author}.")

    @commands.command()
    async def trackinfo(self, ctx, pos: int):
        tracks = self.queue.get_queue(ctx.guild.id)
        if pos < 1 or pos > len(tracks):
            await ctx.send("Invalid track number.")
            logger.warning(f"Invalid trackinfo request by {ctx.author}: {pos}")
            return
        url, title, ctx_obj, duration, requester, search_query = tracks[pos-1]
        mins, secs = divmod(duration, 60)
        embed = discord.Embed(title="Track Information", color=discord.Color.green())
        embed.add_field(name="Track", value=title, inline=False)
        embed.add_field(name="Length", value=f"{mins:02}:{secs:02}", inline=True)
        embed.add_field(name="Position in queue", value=str(pos), inline=True)
        embed.add_field(name="Requested by", value=requester, inline=True)
        await ctx.send(embed=embed)
        logger.info(f"Trackinfo for {title} sent to {ctx.author}.")

    @commands.command()
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused.")
            logger.info(f"Playback paused by {ctx.author}.")

    @commands.command()
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed.")
            logger.info(f"Playback resumed by {ctx.author}.")

    @commands.command()
    async def stop(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            self.queue.clear(ctx.guild.id)
            await ctx.send("Stopped and left the channel.")
            logger.info(f"Playback stopped and bot disconnected by {ctx.author}.")

    @commands.command()
    async def next(self, ctx):
        """Skip to the next song in the queue."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped to the next song.")
            logger.info(f"Skipped to next by {ctx.author}.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command()
    async def prev(self, ctx):
        """Replay the previous song (if available)."""
        # Not implemented: true previous queue, but can replay current
        now_playing = self.queue.get_now_playing(ctx.guild.id)
        if now_playing and now_playing[0]:
            url2, title, ctx_obj, duration, requester, search_query = now_playing
            ctx.voice_client.stop()
            await asyncio.sleep(1)
            ctx.voice_client.play(discord.FFmpegPCMAudio(url2), after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
            await ctx.send(f"Replaying: {title}")
            logger.info(f"Replaying current song by {ctx.author}.")
        else:
            await ctx.send("No song to replay.")

    @commands.command()
    async def repeat(self, ctx):
        """Repeat the current song and clear the queue."""
        now_playing = self.queue.get_now_playing(ctx.guild.id)
        if now_playing and now_playing[0]:
            url2, title, ctx_obj, duration, requester, search_query = now_playing
            self.queue.clear(ctx.guild.id)
            ctx.voice_client.stop()
            await asyncio.sleep(1)
            self.queue.set_now_playing(ctx.guild.id, url2, title, ctx, duration, requester)
            ctx.voice_client.play(discord.FFmpegPCMAudio(url2), after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
            await ctx.send(f"Repeating: {title} and cleared the queue.")
            logger.info(f"Repeat command used by {ctx.author}.")
        else:
            await ctx.send("No song to repeat.")

    @commands.command()
    async def clearqueue(self, ctx):
        """Clear the queue and stop playback."""
        self.queue.clear(ctx.guild.id)
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Queue cleared and playback stopped.")
        logger.info(f"Queue cleared by {ctx.author}.")

    @commands.command()
    async def requestinfo(self, ctx, *, query):
        """Tell the user the position and ETA of a song in the queue."""
        tracks = self.queue.get_queue(ctx.guild.id)
        found = False
        total_time = 0
        for idx, (url, title, ctx_obj, duration, requester, search_query) in enumerate(tracks):
            match_title = (title and query.lower() in title.lower())
            match_url = (url and query.lower() in url.lower())
            match_search = (search_query and query.lower() in search_query.lower())
            if match_title or match_url or match_search:
                found = True
                mins, secs = divmod(duration or 0, 60)
                eta = sum(t[3] or 0 for t in tracks[:idx])
                eta_m, eta_s = divmod(eta, 60)
                display_title = title or search_query or url or "(resolving...)"
                await ctx.send(f"'{display_title}' is at position {idx+1} in the queue. ETA: {eta_m:02}:{eta_s:02} (Length: {mins:02}:{secs:02})")
                logger.info(f"Requestinfo: {display_title} for {ctx.author} at position {idx+1} ETA {eta_m:02}:{eta_s:02}")
                break
            total_time += duration or 0
        if not found:
            await ctx.send("That song is not in the queue.")
            logger.info(f"Requestinfo: {query} not found for {ctx.author}.")

    @commands.command()
    async def shuffle(self, ctx):
        """Shuffle the queue for this guild."""
        import random
        tracks = self.queue.get_queue(ctx.guild.id)
        if not tracks or len(tracks) < 2:
            await ctx.send("Not enough tracks in the queue to shuffle.")
            return
        random.shuffle(tracks)
        self.queue.queues[ctx.guild.id] = tracks
        await ctx.send("Queue shuffled!")
        logger.info(f"Queue shuffled by {ctx.author} in guild {ctx.guild.id}.")

    async def resolve_pending(self, guild_id, ctx):
        loop = ctx.bot.loop
        while True:
            pending = self.queue.next_pending(guild_id)
            if not pending:
                break
            idx, query, ctx_obj, requester = pending
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'default_search': 'ytsearch',
                'noplaylist': False,
                'extract_flat': False,
                'socket_timeout': 30,
            }
            try:
                info = await extract_info_async(loop, query, ydl_opts)
                if 'entries' in info:
                    info = info['entries'][0]
                url2 = info['url']
                title = info.get('title', 'Unknown Title')
                duration = info.get('duration', 0)
                self.queue.mark_resolved(guild_id, idx, url2, title, duration)
                logger.info(f"Resolved pending track: {title} (requested by {requester})")
            except Exception as e:
                logger.error(f"Failed to resolve pending track: {query} - {e}")
                # Optionally, remove or skip this entry
                self.queue.mark_resolved(guild_id, idx, None, f"[Failed: {query}]", 0)
            await asyncio.sleep(1)  # Avoid hammering YouTube

async def setup(bot):
    await bot.add_cog(Music(bot)) 