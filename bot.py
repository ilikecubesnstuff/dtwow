import sys
from configparser import ConfigParser
config = ConfigParser()
config.read(sys.argv[1])

import io
import textwrap
import contextlib

from typing import Optional, Literal, Coroutine

# dependency imports
import discord
from discord import app_commands

# project imports
import db
from db import Twow, TwowState, TwowChannel

from utils.views import EmptyView

# twow game imports
import importlib
game = importlib.import_module(config['game']['preset'])

# logging setup
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
logger = logging.getLogger(config['game']['preset'])
logger.setLevel(logging.DEBUG)  # TODO: Change back to logging.INFO


state_view_map = {
    TwowState.REGISTERING: game.signup.SignUpView,
    TwowState.RESPONDING: game.prompt.SubmissionView,
    TwowState.VOTING: game.vote.VotingView,
    TwowState.IDLE: EmptyView,
    TwowState.HIBERNATING: game.hibernate.HibernationView,
}


class TwowClient(discord.Client):

    def __init__(self, intents, **kwargs):
        super().__init__(intents=intents, **kwargs)
        self.tree = app_commands.CommandTree(self)

        self.twows: dict[int, Twow] = {}

    async def setup_hook(self):
        """
        Database setup & other stuff.
        """
        await db.init()

        async with db.session() as session:
            stmt = db.select(TwowChannel)
            result = await session.scalars(stmt)
            channels: list[TwowChannel] = result.all()

            stmt = db.select(Twow)
            result = await session.scalars(stmt)
            twows: list[Twow] = result.all()

        for channel in channels:
            self.twows[channel.id] = Twow(state=TwowState.HIBERNATING)

        twows = [twow for twow in twows if any(channel.current_twow_id == twow.id for channel in channels)]
        for twow in twows:
            self.twows[twow.channel_id] = twow
            view_cls = state_view_map[twow.state]
            self.add_view(view_cls(twow), message_id=twow.current_message_id)

        MY_GUILD = discord.Object(id=int(config['test server']['id']))
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

    async def on_ready(self):
        await self.change_presence(
            status=getattr(discord.Status, config['discord']['status']),
            activity=discord.Game(
                name=config['activity']['text'],
                type=getattr(discord.ActivityType, config['activity']['type'])
            )
        )

        logger.info(f'Connected! {len(self.twows)} TWOW(s) across {len(self.guilds)} server(s).')
        for channel, twow in self.twows.items():
            logger.debug(f'{channel} {twow.state}')

        self.cmds = {ac.name: ac for ac in await self.tree.fetch_commands()}
        logger.info(f'This client has {len(self.cmds)} global commands.')

intents = discord.Intents.none()
intents.guilds = True
client = TwowClient(intents=intents)

def info_chip(interaction: discord.Interaction):
    """
    Prints interaction state for logging purposes.
    """
    return f'[{interaction.guild.name} | {interaction.channel.name} | {interaction.user.name}]'

def format_cmd(name: str):
    """
    Mentions command of a particular name.
    """
    cmd = client.cmds[name]
    return f'</{cmd.name}:{cmd.id}>'


# public commands

@client.tree.command()
@app_commands.guild_only()
async def help(interaction: discord.Interaction):
    """
    Confused about TWOW? Let me explain it to you!
    """
    twow_host_ids = []  # TODO: maybe cache this part somehow
    async with db.engine.connect() as conn:
        async for twow_channel in await conn.stream(db.select(TwowChannel)):
            twow_host_ids.append(twow_channel.host_id)

    is_admin = interaction.user.resolved_permissions.administrator
    is_twow_host = any(any(host_id == role.id for role in interaction.user.roles) for host_id in twow_host_ids)
    embed = discord.Embed(
        title = 'Help Menu',
        description = 'I am an [open source](https://github.com/ilikecubesnstuff/dtwow) bot created by <@279567692334235649>.\n' + \
                      'I adapt the game Ten Words of Wisdom (TWOW) created by [carykh](https://www.youtube.com/@carykh).\n' + \
                      'Note: An admin is required to activate TWOW in a text channel.'
    )
    if not is_admin and not is_twow_host:
        embed.description = 'I am an [open source](https://github.com/ilikecubesnstuff/dtwow) bot created by <@279567692334235649>.\n' + \
                            'I adapt the game Ten Words of Wisdom (TWOW) created by [carykh](https://www.youtube.com/@carykh).\n' + \
                            'The rules are explained in [episode 0A](https://youtu.be/S64R-_LVHuY) on his YouTube channel.\n' + \
                            'This bot adapts a few rules to make the format Discord-friendly.\n' + \
                            '- Participants are given a prompt to respond to in 10 words.\n' + \
                            '- Everyone then votes for their favorite responses.\n' + \
                            '- Participants earn a score based on their ranking.\n' + \
                            '- For the IB server, these rounds continue analogous to IB subject grades until a maximum score of 45 is reached.\n' + \
                            'Join the TWOW channel to participate!\n' + \
                            'Note: An admin is required to activate TWOW in a text channel.'

    for command in client.tree.walk_commands():
        if command.name in ['eval', 'viewtable', 'sync']:
            continue
        if command.name in ['activate', 'deactivate']:
            if is_admin:
                embed.add_field(
                    name = format_cmd(command.name),
                    value = 'Admin-only command. ' + command.description,
                    inline = False
                )
            continue
        if command.name in ['signup', 'prompt', 'vote', 'conclude', 'recalculate', 'display', 'hibernate']:
            if is_twow_host:
                embed.add_field(
                    name = format_cmd(command.name),
                    value = 'TWOW host command. ' + command.description,
                    inline = False
                )
            continue
        embed.add_field(
            name = format_cmd(command.name),
            value = command.description,
            inline = False
        )

    await interaction.response.send_message(embed=embed)


@client.tree.command()
@app_commands.guild_only()
async def info(interaction: discord.Interaction):
    """
    Status of TWOWs in this server.
    """
    embed = discord.Embed(
        title = 'Info Menu',
        description = 'I am an [open source](https://github.com/ilikecubesnstuff/dtwow) bot created by <@279567692334235649>.\n' + \
                      'I adapt the game Ten Words of Wisdom (TWOW) created by [carykh](https://www.youtube.com/@carykh).\n' + \
                      'The rules are explained in [episode 0A](https://youtu.be/S64R-_LVHuY) on his YouTube channel.\n' + \
                      'This bot adapts a few rules to make the format Discord-friendly.\n' + \
                      '- Participants are given a prompt to respond to in 10 words.\n' + \
                      '- Everyone then votes for their favorite responses.\n' + \
                      '- Participants earn a score based on their ranking.\n' + \
                      '- For the IB server, these rounds continue analogous to IB subject grades until a maximum score of 45 is reached.\n\n'
    )
    if not client.twows:
        embed.description += 'No currently running TWOWs.'
        await interaction.response.send_message(embed=embed)
        return

    embed.description += 'Current running TWOWs:'
    for channel_id, twow in client.twows.items():
        if twow.state == TwowState.HIBERNATING: continue
        if twow.state == TwowState.REGISTERING: value = f'Sign-ups open!'
        if twow.state == TwowState.RESPONDING : value = f'Round {twow.current_round} prompt.'
        if twow.state == TwowState.VOTING     : value = f'Round {twow.current_round} voting.'
        if twow.state == TwowState.IDLE       : value = f'Round {twow.current_round} finished.'
        embed.add_field(
            name = f'<#{channel_id}>',
            value = value
        )

    await interaction.response.send_message(embed=embed)


# administrative commands

@client.tree.command()
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
@app_commands.describe(host='TWOW host role. (Users with this role must have permission to manage threads in this channel.)')
async def activate(interaction: discord.Interaction, host: discord.Role):
    """
    Allow TWOW seasons to take place in a channel. Must assign a role as TWOW host.
    """
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(f'🚫 TWOW only works in text channels.')
        logger.warning(f'{info_chip(interaction)} Activation attempted in an unsupported channel.')
        return

    if interaction.channel_id in client.twows:
        await interaction.response.send_message(f'🚫 TWOW already active in this channel. Please use {format_cmd("signup")} to start TWOW here.')
        state = client.twows[interaction.channel_id].state.name
        logger.warning(f'{info_chip(interaction)} Activation attempted while {state}. {state} state preserved.')
        return

    twow_channel = TwowChannel(id=interaction.channel_id, host_id=host.id)
    client.twows[interaction.channel_id] = Twow(state=TwowState.HIBERNATING)
    async with db.session() as session, session.begin():
        session.add(twow_channel)
    await interaction.response.send_message('TWOW activated!')
    logger.info(f'{info_chip(interaction)} TWOW activated, state set to HIBERNATING.')


@client.tree.command()
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def deactivate(interaction: discord.Interaction):
    """
    Disallow TWOW season to take place in a channel. This will end on-going TWOW seasons.
    """
    if interaction.channel_id not in client.twows:
        await interaction.response.send_message(f'🚫 TWOW already inactive in this channel. Please use {format_cmd("activate")} to activate TWOW here.')
        logger.warning(f'{info_chip(interaction)} INACTIVE attempted while INACTIVE. INACTIVE state preserved.')
        return

    # disable old view
    twow = client.twows[interaction.channel_id]
    if twow.current_message_id:
        old_message = await interaction.channel.fetch_message(twow.current_message_id)
        old_view_cls = state_view_map[twow.state]
        view = old_view_cls(twow)
        for item in view.children:
            item.disabled = True
        await old_message.edit(content=old_message.content, view=view)
        view.stop()

    twow_channel = await db.fetch_by_id(TwowChannel, interaction.channel_id)
    if interaction.channel_id in client.twows:
        del client.twows[interaction.channel_id]
    async with db.session() as session, session.begin():
        await session.delete(twow_channel)
    await interaction.response.send_message('TWOW deactivated!')
    logger.info(f'{info_chip(interaction)} TWOW deactivated, state set to INACTIVE.')


# host commands (requires manage thread permissions)

async def twow_cmd(
        interaction: discord.Interaction,
        new_state: TwowState,
        invalid_entry_dict: dict[TwowState, str],
        message_content: str,
        view_cls,
        db_func: Coroutine):
    """
    Execute a valid step forward in the TWOW process. This is only called through application commands in this file.
    """
    if interaction.channel_id not in client.twows:
        await interaction.response.send_message(f'🚫 TWOW is not active in this channel. Please use {format_cmd("activate")} to activate TWOW here.')
        logger.warning(f'{info_chip(interaction)} {new_state.name} attempted while INACTIVE. INACTIVE state preserved.')
        return

    twow = client.twows[interaction.channel_id]
    for state, message in invalid_entry_dict.items():
        if twow.state == state:
            await interaction.response.send_message(message, ephemeral=True)
            logger.warning(f'{info_chip(interaction)} {new_state.name} attempted while {state.name} was active. {state.name} state preserved.')
            return
    logger.info(f'{info_chip(interaction)} Changing state from {twow.state.name} to {new_state.name}.')

    # disable old view
    if twow.current_message_id:
        old_message = await interaction.channel.fetch_message(twow.current_message_id)
        old_view_cls = state_view_map[twow.state]
        view = old_view_cls(twow)
        for item in view.children:
            item.disabled = True
        await old_message.edit(content=old_message.content, view=view)
        view.stop()

    # create new TWOW if necessary
    if new_state == TwowState.REGISTERING:
        async with db.session() as session:
            twow_channel = await session.get(TwowChannel, interaction.channel_id)
            twow = Twow(
                guild_id = interaction.guild_id,
                channel_id = interaction.channel_id,
                current_round = 0,
                state = TwowState.REGISTERING
            )
            session.add_all([twow_channel, twow])
            await session.commit()

            twow_channel.current_twow_id = twow.id
            await session.commit()
        client.twows[interaction.channel_id] = twow

    view = view_cls(twow)
    await interaction.response.send_message(message_content(twow), view=view)
    message = await interaction.original_response()
    async with db.session() as session:
        session.add(twow)
        await db_func(session, twow, message)
        await session.commit()
    logger.info(f'{info_chip(interaction)} State set to {new_state.name}.')

    return twow


@client.tree.command()
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
@app_commands.describe(prompt='Prompt given to server members for the sign-up round.')
async def signup(interaction: discord.Interaction, prompt: str):
    """
    Create a new TWOW season and open sign-ups with a prompt.
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.current_round = 0
        twow.state = TwowState.REGISTERING

    await twow_cmd(
        interaction,
        new_state=TwowState.REGISTERING,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW sign-ups are already open!',
            TwowState.RESPONDING: '🚫 Cannot open sign-ups in the middle of a TWOW season.',
            TwowState.VOTING: '🚫 Cannot open sign-ups in the middle of a TWOW season.',
            TwowState.IDLE: '🚫 Cannot open sign-ups in the middle of a TWOW season.'
        },
        message_content=lambda twow: f'TWOW sign-ups are open! (ID: {twow.id})\nRound {twow.current_round} Prompt:\n# {prompt}',
        view_cls=game.signup.SignUpView,
        db_func=db_entry_update
    )


@client.tree.command()
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
@app_commands.describe(prompt='Prompt given to participants for the TWOW round.')
async def prompt(interaction: discord.Interaction, prompt: str):
    """
    Begin a new TWOW round with a prompt.
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.current_round += 1
        twow.state = TwowState.RESPONDING

    await twow_cmd(
        interaction,
        new_state=TwowState.RESPONDING,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW sign-ups are active! Cannot post new prompt.',
            TwowState.RESPONDING: '🚫 TWOW round is already active! Cannot post new prompt.',
            TwowState.VOTING: f'🚫 Voting is open! Please {format_cmd("conclude")} voting before posting a new prompt.',
            TwowState.HIBERNATING: f'🚫 No TWOW season. To start a new TWOW season, use {format_cmd("signup")}.'
        },
        message_content=lambda twow: f'Round {twow.current_round} Prompt:\n# {prompt}',
        view_cls=game.prompt.SubmissionView,  # TODO: fix this
        db_func=db_entry_update
    )


@client.tree.command()
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
async def vote(interaction: discord.Interaction):
    """
    Commence voting for a TWOW round.
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.state = TwowState.VOTING

    await twow_cmd(
        interaction,
        new_state=TwowState.VOTING,
        invalid_entry_dict={
            TwowState.VOTING: '🚫 Voting is already open!',
            TwowState.IDLE: '🚫 No active TWOW round! Cannot commence voting.',
            TwowState.HIBERNATING: '🚫 No active TWOW round! Cannot commence voting.'
        },
        message_content=lambda twow: f'Round {twow.current_round} voting is open!',
        view_cls=game.vote.VotingView,
        db_func=db_entry_update
    )


@client.tree.command()
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
async def conclude(interaction: discord.Interaction):
    """
    Conclude voting for a TWOW round.
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.state = TwowState.IDLE

    twow = await twow_cmd(
        interaction,
        new_state=TwowState.IDLE,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW sign-ups are active! Cannot conclude round until after voting.',
            TwowState.RESPONDING: '🚫 TWOW round is active! Cannot conclude round until after voting.',
            TwowState.IDLE: f'🚫 No active round? Use {format_cmd("prompt")} to start a TWOW round.',
            TwowState.HIBERNATING: f'🚫 No active round? Use {format_cmd("signup")} to start a TWOW season.'
        },
        message_content=lambda twow: f'Round {twow.current_round} voting is now closed.',
        view_cls=EmptyView,  # TODO: fix this
        db_func=db_entry_update
    )

    if twow:
        await game.results.update(twow)

@client.tree.command(name='recalculate')
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
async def recalculate_results(interaction: discord.Interaction):
    """
    Recalculate results for the current TWOW rounds.
    """
    twow = client.twows[interaction.channel_id]
    if twow.state != TwowState.IDLE:
        await interaction.response.send_message(f'🚫 You can only recalculate results after concluding voting.')
        logger.warning(f'{info_chip(interaction)} Result presentation attempted while not IDLE.')
        return
    await game.results.update(twow)
    await interaction.response.send_message('Results recalculated!', ephemeral=True)

@client.tree.command(name='display')
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
async def display_results(interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
    """
    Present results for the current TWOW round.
    """
    await interaction.response.defer(ephemeral=True)

    channel = channel or interaction.channel
    if isinstance(channel, discord.TextChannel):
        channel = await channel.create_thread(name=f'TWOW {twow.id}.{twow.current_round} Results', type=discord.ChannelType.public_thread)
    elif not isinstance(channel, discord.Thread):
        await interaction.followup.send('Invalid channel type.', ephemeral=True)
        return
    elif isinstance(channel.parent, discord.ForumChannel):
        await interaction.followup.send('Cannot use this command in a forum channel!', ephemeral=True)
        return

    twow = client.twows[channel.parent_id]
    if twow.state != TwowState.IDLE:
        await interaction.response.send_message(f'🚫 You can only present results after concluding voting.')
        logger.warning(f'{info_chip(interaction)} Result presentation attempted while not IDLE.')
        return

    status = await game.results.display(twow, channel)
    await interaction.followup.send(status, ephemeral=True)


@client.tree.command()
@app_commands.default_permissions(manage_threads=True)
@app_commands.guild_only()
async def hibernate(interaction: discord.Interaction):
    """
    Hibernate TWOW in this channel. (This opens prompt & feedback submission between seasons.)
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.state = TwowState.HIBERNATING

    await twow_cmd(
        interaction,
        new_state=TwowState.HIBERNATING,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW round active! Cannot hibernate until after round is over.',
            TwowState.RESPONDING: '🚫 TWOW round active! Cannot hibernate until after round is over.',
            TwowState.VOTING: '🚫 TWOW round active! Cannot hibernate until after round is over.',
            TwowState.HIBERNATING: '🚫 Already hibernating!'
        },
        message_content=lambda twow: f'After {twow.current_round} rounds, this TWOW season is over!',
        view_cls=game.hibernate.HibernationView,
        db_func=db_entry_update
    )


# developer commands

@client.tree.command(name='eval')
@app_commands.default_permissions(administrator=True)
@app_commands.guilds(int(config['test server']['id']))
async def evaluate(interaction: discord.Interaction, code: str):
    """
    Run a line of arbitrary python code.
    """
    local_variables = {
        'discord': discord,
        'client': interaction.client,
        'interaction': interaction,
        'channel': interaction.channel,
        'user': interaction.user,
        'guild': interaction.guild,
        'message': interaction.message,
        'db': db,
        'game': game,
    }

    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(
                f'async def func():\n{textwrap.indent(code, "    ")}', local_variables,
            )

            obj = await local_variables['func']()
            result = f'{stdout.getvalue()}\n-- {obj}\n'
    except Exception as e:
        await interaction.response.send_message(e)
        raise RuntimeError(e)
    await interaction.response.send_message(result[0:2000])


@client.tree.command()
@app_commands.default_permissions(administrator=True)
@app_commands.guilds(int(config['test server']['id']))
async def viewtable(interaction: discord.Interaction, name: Literal['participant', 'response', 'vote', 'twow', 'twowchannel']):
    """
    View one of the tables stored in the database.
    """
    cls = {
        'participant': game.tables.Participant,
        'response': game.tables.Response,
        'vote': game.tables.Vote,
        'twow': Twow,
        'twowchannel': TwowChannel
    }[name]
    async with db.session() as session, session.begin():
        stmt = db.select(cls)
        entries = (await session.scalars(stmt)).all()
    await interaction.response.send_message('```' + '\n'.join(repr(entry) for entry in entries) + '```')


@client.tree.command()
@app_commands.default_permissions(administrator=True)
@app_commands.guilds(int(config['test server']['id']))
async def sync(interaction: discord.Interaction):
    """
    Sync global app commands to discord.
    """
    app_commands = await client.tree.sync()
    await interaction.response.send_message(f'Synced {len(app_commands)} commands!')


client.run(config['discord']['token'])