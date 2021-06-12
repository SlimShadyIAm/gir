from datetime import datetime, timedelta
import discord 
import asyncio
from discord.ext import commands
import pytimeparse

class PromptData:
    def __init__(self, value_name, description, convertor, title=None, reprompt=False):
        self.value_name = value_name
        self.description = description
        self.convertor = convertor
        self.title = title
        self.reprompt = reprompt

class Context(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = self.bot.settings
        self.permissions = self.bot.settings.permissions
        self.tasks = self.bot.settings.tasks
        
    async def send_success(self, description: str, delete_after: int = None):
        return await self.reply(embed=discord.Embed(description=description, color=discord.Color.blurple()), delete_after=delete_after)
    
    async def prompt(self, info: PromptData):
        def wait_check(m):
            return m.author == self.author and m.channel == self.channel
    
        ret = None
        embed = discord.Embed(
            title=info.title if not info.reprompt else f"That wasn't a valid {info.value_name}. {info.title if info.title is not None else ''}",
            description=info.description,
            color=discord.Color.blurple())
        embed.set_footer(text="Send 'cancel' to cancel.")
        
        prompt_msg = await self.send(embed=embed)
        try:
            response = await self.bot.wait_for('message', check=wait_check, timeout=120)
        except asyncio.TimeoutError:
            await prompt_msg.delete()
            return
        else:
            await response.delete()
            await prompt_msg.delete()
            if response.content.lower() == "cancel":
                return
            elif response.content is not None and response.content != "":
                if info.convertor in [str, int, pytimeparse.parse]:
                    try:
                        ret = info.convertor(response.content)
                    except Exception:
                        ret = None
                    
                    if ret is None:
                        info.reprompt = True
                        return await self.prompt(info)

                    if info.convertor is pytimeparse.parse:
                        now = datetime.now()
                        time = now + timedelta(seconds=ret)
                        if time < now:
                            raise commands.BadArgument("Time has to be in the future >:(")

                else:
                    ret = await info.convertor(self, response.content)
                    
        return ret

        
    async def send_error(self, error):
        embed = discord.Embed(title=":(\nYour command ran into a problem")
        embed.color = discord.Color.red()
        embed.description = discord.utils.escape_markdown(f'{error}')
        await self.send(embed=embed, delete_after=8)
