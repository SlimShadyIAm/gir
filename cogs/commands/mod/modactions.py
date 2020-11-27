import discord
from discord.ext import commands
import cogs.utils.logs as logging
from data.case import Case
import traceback
import typing
import datetime
import pytimeparse

# async def check_permissions(self, ctx, user: typing.Union[discord.Member, int]):
async def check_permissions( ctx):
    user = ctx.args[2]
    if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6): # must be at least a mod
        raise commands.BadArgument("You need to be a moderator or higher to use that command.")
    if isinstance(user, discord.Member): # 
        if user.top_role >= ctx.author.top_role:
            raise commands.BadArgument(message=f"{user}'s top role is the same or higher than yours!")
    
    # return True

class ModActions(commands.Cog):
    """This cog handles all the possible moderator actions.
    - Kick
    - Ban
    - Unban
    - Warn
    - Liftwarn
    - Mute
    - Unmute
    - Purge
    """

    def __init__(self, bot):    
        self.bot = bot

    @commands.guild_only()
    @commands.check(check_permissions)
    @commands.command(name="warn")
    async def warn(self, ctx: commands.Context, user: discord.Member, points: int, *, reason: str = "No reason.") -> None:
        """!warn <@user/ID> <points> <reason>

        Parameters
        ----------
        ctx : commands.Context
            Context in which the command was invoked
        user : discord.Member
            The member to warn
        points : int
            Number of points to warn far
        reason : str, optional
            Reason for warning, by default "No reason."

        Raises
        ------
        commands.BadArgument
            If one of the command arguments is not properly defined, lacking permissions, etc.
        """        

        await ctx.message.delete()

        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6): # must be at least a mod
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        if points < 1: # can't warn for negative/0 points
            raise commands.BadArgument(message="Points can't be lower than 1.")
        if user.top_role >= ctx.author.top_role: # the punishee must have a lower top role than punisher
            raise commands.BadArgument(message=f"{user}'s top role is the same or higher than yours!")
        
        guild = self.bot.settings.guild()
        
        # prepare the case object for database
        case = Case(
            _id = guild.case_id,
            _type = "WARN",
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
            punishment_points=points
        )

        # increment case ID in database for next available case ID
        await self.bot.settings.inc_caseid()
        # add new case to DB
        await self.bot.settings.add_case(user.id, case)
        # add warnpoints to the user in DB
        await self.bot.settings.inc_points(user.id, points)

        # fetch latest document about user from DB
        results = await self.bot.settings.user(user.id)
        cur_points = results.warn_points

        # prepare log embed, send to #public-mod-logs, user, channel where invoked
        log = await logging.prepare_warn_log(ctx, user, case)
        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        if public_chan:
            await public_chan.send(embed=log)  

        log.add_field(name="Current points", value=cur_points, inline=True)
        # also send response in channel where command was called
        await ctx.send(embed=log)

        if cur_points >= 600: 
            # automatically ban user if more than 600 points
            await ctx.invoke(self.ban, user=user, reason="600 or more points reached")
        elif cur_points >= 400 and not results.was_warn_kicked: 
            # kick user if >= 400 points and wasn't previously kicked
            await self.bot.settings.set_warn_kicked(user.id)
            
            try:
                await user.send("You were kicked from r/Jailbreak for reaching 400 or more points.", embed=log)
            except Exception:
                pass
            
            await ctx.invoke(self.kick, user=user, reason="400 or more points reached")
        else:
            try:
                await user.send("You were warned in r/Jailbreak.", embed=log)      
            except Exception:
                pass
    
    @commands.guild_only()
    @commands.command(name="liftwarn")
    async def liftwarn(self, ctx: commands.Context, user: discord.Member, case_id: int, *, reason: str = "No reason.") -> None:
        """!liftwarn <@user/ID> <case ID> <reason>

        Parameters
        ----------
        ctx : commands.Context
            Context in which command was invoked
        user : discord.Member
            User to remove warn from
        case_id : int
            The ID of the case for which we want to remove points
        reason : str, optional
            Reason for lifting warn, by default "No reason."

        Raises
        ------
        commands.BadArgument
            If one of the command arguments is not properly defined, lacking permissions, etc.
        """        

        await ctx.message.delete()

        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6): # must be at least a mod
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        if user.top_role >= ctx.author.top_role: # punisher must have higher top role than punishee
            raise commands.BadArgument(message=f"{user}'s top role is the same or higher than yours!")

        # retrieve user's case with given ID
        cases = await self.bot.settings.get_case(user.id, case_id)
        case = cases.cases.filter(_id=case_id).first()
        
        # sanity checks
        if case is None:
            raise commands.BadArgument(message=f"{user} has no case with ID {case_id}")
        elif case._type != "WARN":
            raise commands.BadArgument(message=f"{user}'s case with ID {case_id} is not a warn case.")
        elif case.lifted:
            raise commands.BadArgument(message=f"Case with ID {case_id} already lifted.")
        
        # passed sanity checks, so update the case in DB
        case.lifted = True
        case.lifted_reason = reason
        case.lifted_by_tag = str(ctx.author)
        case.lifted_by_id = ctx.author.id
        case.lifted_date = datetime.datetime.now()
        cases.save()

        # remove the warn points from the user in DB
        await self.bot.settings.inc_points(user.id, -1 * case.punishment_points)

        # prepare log embed, send to #public-mod-logs, user, channel where invoked
        log = await logging.prepare_liftwarn_log(ctx, user, case)
        try:
            await user.send("Your warn was lifted in r/Jailbreak.", embed=log)      
        except Exception:
            pass
        
        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        if public_chan:
            await public_chan.send(embed=log)  
        
        await ctx.send(embed=log)
    
    @commands.guild_only()
    @commands.command(name="kick")
    async def kick(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason.") -> None:
        """!kick <@user/ID> <reason>

        Parameters
        ----------
        ctx : commands.Context
            Context in which command was invoked
        user : discord.Member
            User to kick
        reason : str, optional
            Reason for kick, by default "No reason."

        Raises
        ------
        commands.BadArgument
            If one of the command arguments is not properly defined, lacking permissions, etc.
        """        

        await ctx.message.delete()
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6): # must be at least a mod
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        if user.top_role >= ctx.author.top_role: # make sure punisher has higher top role than punishee
            raise commands.BadArgument(message=f"{user}'s top role is the same or higher than yours!")
        
        # prepare case for DB
        case = Case(
            _id = self.bot.settings.guild().case_id,
            _type = "KICK",
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
        )

        # increment max case ID for next case
        await self.bot.settings.inc_caseid()
        # add new case to DB
        await self.bot.settings.add_case(user.id, case)

        # prepare log embed, send to #public-mod-logs, user, context
        log = await logging.prepare_kick_log(ctx, user, case)
        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        await public_chan.send(embed=log)
        await ctx.send(embed=log)
        try:
            await user.send("You were kicked from r/Jailbreak", embed=log)
        except Exception:
            pass

        await user.kick(reason=reason)
    
    @commands.guild_only()
    # @commands.check(self.ch)
    @commands.command(name="ban")
    async def ban(self, ctx: commands.Context, user: typing.Union[discord.Member, int], *, reason: str = "No reason."):
        """!ban <@user/ID> <reason>

        Parameters
        ----------
        ctx : commands.Context
            Context where command was called
        user : typing.Union[discord.Member, int]
            The user to be banned, doesn't have to be part of the guild
        reason : str, optional
            Reason for ban, by default "No reason."

        Raises
        ------
        commands.BadArgument
            If one of the command arguments is not properly defined, lacking permissions, etc.
        """        

        await ctx.message.delete()
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6): # must be at least a mod
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        if isinstance(user, discord.Member): # punishee's top role must be lower than punisher's
            if user.top_role >= ctx.author.top_role:
                raise commands.BadArgument(message=f"{user}'s top role is the same or higher than yours!")
        
        # if the ID given is of a user who isn't in the guild, try to fetch the profile
        if isinstance(user, int):
            try:
                user = await self.bot.fetch_user(user)
            except discord.NotFound:
                raise commands.BadArgument(f"Couldn't find user with ID {user}")
        
        # prepare the case to store in DB
        case = Case(
            _id = self.bot.settings.guild().case_id,
            _type = "BAN",
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
        )

        # increment DB's max case ID for next case
        await self.bot.settings.inc_caseid()
        await self.bot.settings.add_case(user.id, case)

        # prepare log embed to send to #public-mod-logs, user and context
        log = await logging.prepare_ban_log(ctx, user, case)
        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        await public_chan.send(embed=log)
        await ctx.send(embed=log)
        
        try:
            await user.send("You were banned from r/Jailbreak", embed=log)
        except Exception:
            pass
        
        if isinstance(user, discord.Member):
            await user.ban(reason=reason)
        else:
            # hackban for user not currently in guild
            await ctx.guild.ban(discord.Object(id=user.id))

    @commands.guild_only()
    @commands.command(name="unban")
    async def unban(self, ctx: commands.Context, user: int, *, reason: str = "No reason.") -> None:
        """!unban <user ID> <reason> 

        Parameters
        ----------
        ctx : commands.Context
            Context where command was invoked
        user : int
            ID of the user to unban
        reason : str, optional
            Reason for unban, by default "No reason."

        Raises
        ------
        commands.BadArgument
            If one of the command arguments is not properly defined, lacking permissions, etc.
        """        

        await ctx.message.delete()
        
        try:
            user = await self.bot.fetch_user(user)
        except discord.NotFound:
            raise commands.BadArgument(f"Couldn't find user with ID {user}")
        
        try:
            await ctx.guild.unban(discord.Object(id=user.id))
        except discord.NotFound:
            raise commands.BadArgument(f"{user} is not banned.")
        
        case = Case(
            _id = self.bot.settings.guild().case_id,
            _type = "UNBAN",
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
        )
        await self.bot.settings.inc_caseid()
        await self.bot.settings.add_case(user.id, case)

        log = await logging.prepare_unban_log(ctx, user, case)

        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        await public_chan.send(embed=log)
        await ctx.send(embed=log)
                

    @commands.guild_only()
    @commands.command(name="purge")
    async def purge(self, ctx, limit: int = 0):
        await ctx.message.delete()
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6):
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        if limit <= 0:
            raise commands.BadArgument("Number of messages to purge must be greater than 0")
        await ctx.channel.purge(limit=limit)
        await ctx.send(f'Purged {limit} messages.')
    
    @commands.guild_only()
    @commands.command(name="mute")
    async def mute(self, ctx, user:discord.Member, dur:str, *, reason : str = "No reason."):
        await ctx.message.delete()
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6):
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        
        delta = pytimeparse.parse(dur)
        if delta is None:
            raise commands.BadArgument("Failed to parse time duration.")

        time = datetime.datetime.now() + datetime.timedelta(seconds=delta)
        
        mute_role = self.bot.settings.guild().role_mute
        mute_role = ctx.guild.get_role(mute_role)
        await user.add_roles(mute_role)        
        
        try:
            self.bot.settings.tasks.schedule_unmute(user.id, time)
        except Exception:
            raise commands.BadArgument("An error occured, this user is probably already muted")

        case = Case(
            _id = self.bot.settings.guild().case_id,
            _type = "MUTE",
            until=time,
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
        )
        await self.bot.settings.inc_caseid()
        await self.bot.settings.add_case(user.id, case)

        log = await logging.prepare_mute_log(ctx, user, case)

        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        await public_chan.send(embed=log)
        await ctx.send(embed=log)

        try:
            await user.send("You have been muted in r/Jailbreak", embed=log)
        except:
            pass

    @commands.guild_only()
    @commands.command(name="unmute")
    async def unmute(self, ctx, user:discord.Member, *, reason: str = "No reason."):
        await ctx.message.delete()
        if not self.bot.settings.permissions.hasAtLeast(ctx.guild, ctx.author, 6):
            raise commands.BadArgument("You need to be a moderator or higher to use that command.")
        
        mute_role = self.bot.settings.guild().role_mute
        mute_role = ctx.guild.get_role(mute_role)
        await user.remove_roles(mute_role)   

        try:
            self.bot.settings.tasks.cancel_unmute(user.id)
        except Exception:
            pass

        case = Case(
            _id = self.bot.settings.guild().case_id,
            _type = "UNMUTE",
            mod_id=ctx.author.id,
            mod_tag = str(ctx.author),
            reason=reason,
        )
        await self.bot.settings.inc_caseid()
        await self.bot.settings.add_case(user.id, case)

        log = await logging.prepare_unmute_log(ctx, user, case)

        public_chan = discord.utils.get(ctx.guild.channels, id=self.bot.settings.guild().channel_public)
        await public_chan.send(embed=log)
        await ctx.send(embed=log)

        try:
            await user.send("You have been unmuted in r/Jailbreak", embed=log)
        except:
            pass
    
    @unmute.error                    
    @mute.error
    @liftwarn.error
    @unban.error
    @ban.error
    @warn.error
    @purge.error
    @kick.error
    async def info_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await(ctx.send(error, delete_after=5))
        elif isinstance(error, commands.BadArgument):
            await(ctx.send(error, delete_after=5))
        elif isinstance(error, commands.MissingPermissions):
            await(ctx.send(error, delete_after=5))
        elif isinstance(error, commands.NoPrivateMessage):
            await(ctx.send(error, delete_after=5))
        else:
            traceback.print_exc()

def setup(bot):
    bot.add_cog(ModActions(bot))

# !warn
# !lfitwarn
# !kick
# !ban
# !mute
# !clem
# !purge