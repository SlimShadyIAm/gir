import discord
from discord.ext import commands
import io
import aiohttp
import re
from enum import Enum
import traceback


class EmojiType(Enum):
    Bad = 1
    Emoji = 2
    Image = 3
    
        
class BoosterEmojis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='auditemojis', hidden=True)
    async def auditemojis(self, ctx: commands.Context):
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 7):
            raise commands.BadArgument(
                "You need to be Aaron to use that command.")

        channel = ctx.guild.get_channel(self.bot.settings.guild().channel_booster_emoji)
        if not channel:
            return
        
        await ctx.message.delete()
        count = 0
        async for msg in channel.history():
            try:
                _bytes, _ = await self.get_bytes(msg)
            except commands.BadArgument:
                await self.add_reactions(False, msg)
                continue
            
            if _bytes is not None:
                await self.add_reactions(True, msg)
                count += 1
            else:
                await self.add_reactions(False, msg)

            # emoji = custom_emojis[0]
            # byte = await emoji.url.read()
            # await channel.guild.create_custom_emoji(image=byte, name=emoji.name)
        await ctx.send(f"Found {count} emojis and added reacts for them.", delete_after=5)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.member:
            return
        if not payload.member.guild:
            return
        if payload.member.bot:
            return
        channel = payload.member.guild.get_channel(payload.channel_id)
        try:
            msg = await channel.fetch_message(payload.message_id)
        except:
            return
        db = self.bot.settings
        
        if not msg.guild.id == db.guild_id:
            return
        if not payload.channel_id == db.guild().channel_booster_emoji:
            return
        if payload.channel_id != self.bot.settings.guild().channel_booster_emoji:
            return
        if not str(payload.emoji) in ['✅', '❌']:
            return
        if not self.bot.settings.permissions.hasAtLeast(payload.member.guild, payload.member, 7):
            await msg.remove_reaction(payload.emoji, payload.member)
            return

        if str(payload.emoji) == '❌':
            await msg.delete()
            return

        try:
            _bytes, name = await self.get_bytes(msg)
        except commands.BadArgument as e:
            await msg.channel.send(e, delete_after=5)
            await msg.delete(delay=5)
            return

        if _bytes is None:
            await msg.remove_reaction(payload.emoji, payload.member)
            return
        
        if name is None:
            def check(m):
                return m.author == payload.member
            
            while True:
                prompt = await channel.send("Enter name for emoji")
                temp = await self.bot.wait_for('message', check=check)
                name = temp.content
                await prompt.delete()
                await temp.delete()
                if len(name) > 2 and len(name) < 20:
                    break

        emoji = await channel.guild.create_custom_emoji(image=_bytes, name=name)
        if emoji:
            await msg.delete()
        await payload.member.send(emoji)


    @commands.Cog.listener()
    async def on_message(self, msg):
        if not msg.guild:
            return
        db = self.bot.settings
        if msg.author.bot:
            return
        if not msg.guild.id == db.guild_id:
            return
        if not msg.channel.id == db.guild().channel_booster_emoji:
            return
        
        try:
            _bytes, _ = await self.get_bytes(msg)
        except commands.BadArgument as e:
            await msg.reply(e, delete_after=5)
            await msg.delete(delay=5)
            return

        await self.add_reactions(good=_bytes is not None, msg=msg)

    async def get_bytes(self, msg):
        custom_emojis = re.findall(r'<:\d+>|<:.+?:\d+>', msg.content)
        if len(custom_emojis) == 1:
            name = custom_emojis[0].split(':')[1]
        custom_emojis = [int(e.split(':')[2].replace('>', '')) for e in custom_emojis]
        custom_emojis = [f"https://cdn.discordapp.com/emojis/{e}.png?v=1" for e in custom_emojis]
        
        custom_emojis_gif = re.findall(r'<a:.+:\d+>|<:.+?:\d+>', msg.content)
        if len(custom_emojis_gif) == 1:
            name = custom_emojis_gif[0].split(':')[1]
        custom_emojis_gif = [int(e.split(':')[2].replace('>', '')) for e in custom_emojis_gif]
        custom_emojis_gif = [f"https://cdn.discordapp.com/emojis/{e}.gif?v=1" for e in custom_emojis_gif]
        pattern = re.compile(
            r"(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*))")
        link = pattern.search(msg.content)
        if (link):
            if link.group(0):
                link = link.group(0)

        if len(custom_emojis) > 1 or len(custom_emojis_gif) > 1 or len(msg.attachments) > 1:
            return None
        elif len(custom_emojis) == 1:
            emoji = custom_emojis[0]
            return await self.do_content_parsing(emoji), name
        elif len(custom_emojis_gif) == 1:
            emoji = custom_emojis_gif[0]
            return await self.do_content_parsing(emoji), name
        elif len(msg.attachments) == 1:
            url = msg.attachments[0].url
            return await self.do_content_parsing(url), None
        elif link:
            return await self.do_content_parsing(link), None
        else:
            return None, None

    async def add_reactions(self, good: bool, msg: discord.Message):
        if good:
            await msg.add_reaction('✅')
            await msg.add_reaction('❌')
        else:
            await msg.add_reaction('❓')

    async def do_content_parsing(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as resp:
                if resp.status != 200:
                    return None
                elif resp.headers["CONTENT-TYPE"] not in ["image/png", "image/jpeg", "image/gif", "image/webp"]:
                    return None
                elif int(resp.headers['CONTENT-LENGTH']) > 257000:
                    raise commands.BadArgument(f"Image was too big ({int(int(resp.headers['CONTENT-LENGTH'])/1000)}KB)")
                else:
                    async with session.get(url) as resp2:
                        if resp2.status != 200:
                            return None

                        return await resp2.read()

    @auditemojis.error
    async def info_error(self, ctx, error):
        await ctx.message.delete(delay=5)
        if (isinstance(error, commands.MissingRequiredArgument)
            or isinstance(error, commands.BadArgument)
            or isinstance(error, commands.BadUnionArgument)
            or isinstance(error, commands.BotMissingPermissions)
            or isinstance(error, commands.MissingPermissions)
                or isinstance(error, commands.NoPrivateMessage)):
            await self.bot.send_error(ctx, error)
        else:
            await self.bot.send_error(ctx, error)
            traceback.print_exc()


def setup(bot):
    bot.add_cog(BoosterEmojis(bot))
