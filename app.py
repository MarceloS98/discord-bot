import asyncio
import os
import discord
import yt_dlp
import subprocess
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn -b:a 128k -bufsize 2000k',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'executable': 'ffmpeg',
    'stderr': subprocess.PIPE 
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume) 

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot, song_queue = []):
        self.bot = bot
        self.song_queue = song_queue

    @commands.command()
    async def play(self, ctx, *, url):
        """Streams from a url"""
        
        async with ctx.typing(): # show typing while processing
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True) # create a player from the url
            self.song_queue.append(player)

        if not ctx.voice_client.is_playing():
            await self.play_song(ctx)
        
        await ctx.send(f'{player.title} **added to the queue**') # alert the user that the song was added to the queue

    async def play_song(self, ctx):
        if not self.song_queue:
            await ctx.send('**The queue is empty.** Use `!play` to add a song.')
            return

        player = self.song_queue[1] if len(self.song_queue) > 1 else self.song_queue[0]
        ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next_song(ctx), self.bot.loop).result())

        await ctx.send(f'**Now playing:** {player.title}')

    async def play_next_song(self, ctx):
        if len(self.song_queue) == 1:
            await ctx.send('**Queue complete.**')
            self.song_queue.pop(0)

        if self.song_queue:
            await self.play_song(ctx)
            self.song_queue.pop(0)

    # Define the skip command to skip to the next song in the queue
    @commands.command()
    async def skip(self, ctx):
        """Skips to the next song in the queue"""

        if not ctx.voice_client.is_playing():
            await ctx.send('**Not playing any music.**')
            return

        ctx.voice_client.stop()
        await self.play_next_song(ctx)

        await ctx.send('**Skipped to the next song.**')

    # Define the next_song function to start playing the first song in the queue
    async def next_song(self, ctx):
        if not self.song_queue:
            await ctx.send('**The queue is empty.** Use `!play` to add a song.')
            return

        # Stop the current song
        ctx.voice_client.stop()

        # Play the next song
        player = self.song_queue[0]
        await ctx.send(f'**Now playing:** {player.title}')
        ctx.voice_client.play(self.song_queue[0], after=lambda e: print(f'Player error: {e}') if e else None)

        # Remove the played song from the queue
        self.song_queue.pop(0)


    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("**Not connected** to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"**Changed volume** to {volume}%")

    @commands.command()
    async def pause(self, ctx):
        """Pauses the currently playing song"""
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
        
        await ctx.send('**Song paused.**')

    @commands.command()
    async def resume(self, ctx):
        """Resumes a currently paused song """

        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()

        await ctx.send('**Song resumed.**')
        
    @commands.command()
    async def leave(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke # before play is invoked, ensure_voice is invoked
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    description='Relatively simple music bot example',
    intents=intents,
)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

async def main():
    async with bot:
        await bot.add_cog(Music(bot)) 
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())