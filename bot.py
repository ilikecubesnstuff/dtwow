import sys
from configparser import ConfigParser
config = ConfigParser()
config.read(sys.argv[1])

from typing import Optional, Coroutine

# imports for "eval" command
import io
import textwrap
import contextlib

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

        twows = [twow for twow in twows if any(channel.current_twow_id == twow.id for channel in channels)]
        for twow in twows:
            self.twows[twow.channel_id] = twow
            view_cls = state_view_map[twow.state]
            self.add_view(view_cls(twow), message_id=twow.current_message_id)

        # This copies the global commands over to your guild.
        MY_GUILD = discord.Object(id=1114592296747413504)  # Testing server.
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

        logger.info(f"Connected! {len(self.twows)} TWOW(s) across {len(self.guilds)} server(s).")
        for channel, twow in self.twows.items():
            logger.debug(f"{channel} {twow.state}")

intents = discord.Intents.none()
intents.guilds = True
client = TwowClient(intents=intents)

ACTIVATE_CMD = '</activate:1115921695639863377>'
SIGNUP_CMD = '</signup:1115877522572312587>'


def info_chip(interaction: discord.Interaction):
    return f"[{interaction.guild.name} | {interaction.channel.name} | {interaction.user.name}]"


@client.tree.command()
async def activate(interaction: discord.Interaction, host: discord.Role):
    """
    Allow TWOW seasons to take place in a channel. Must assign a role as TWOW host.
    """
    if interaction.channel_id in client.twows:
        await interaction.response.send_message(f'🚫 TWOW already active in this channel. Please use {SIGNUP_CMD} to start TWOW here.')
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
async def deactivate(interaction: discord.Interaction):
    """
    Disallow TWOW season to take place in a channel. This will end on-going TWOW seasons.
    """
    if interaction.channel_id not in client.twows:
        await interaction.response.send_message(f'🚫 TWOW already inactive in this channel. Please use {ACTIVATE_CMD} to activate TWOW here.')
        logger.warning(f'{info_chip(interaction)} INACTIVE attempted while INACTIVE. INACTIVE state preserved.')
        return

    twow_channel = await db.fetch_by_id(TwowChannel, interaction.channel_id)
    if interaction.channel_id in client.twows:
        del client.twows[interaction.channel_id]
    async with db.session() as session, session.begin():
        await session.delete(twow_channel)
    await interaction.response.send_message('TWOW deactivated!')
    logger.info(f'{info_chip(interaction)} TWOW deactivated, state set to INACTIVE.')


async def twow_cmd(
        interaction: discord.Interaction,
        new_state: TwowState,
        invalid_entry_dict: dict[TwowState, str],
        message_content: str,
        view_cls,
        db_func: Coroutine):
    if interaction.channel_id not in client.twows:
        await interaction.response.send_message(f'🚫 No TWOW present in this channel. Please use {ACTIVATE_CMD} to activate TWOW here.')
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
async def signup(interaction: discord.Interaction, prompt: str):
    """
    Begin a TWOW season.
    """
    async def db_entry_update(session, twow, message):
        twow_channel = await session.get(TwowChannel, interaction.channel_id)
        new_twow = Twow(
            guild_id = interaction.guild_id,
            channel_id = interaction.channel_id,
            current_message_id = message.id,
            current_round = 0,
            state = TwowState.REGISTERING
        )    
        session.add_all([twow_channel, new_twow])
        await session.commit()

        client.twows[interaction.channel_id] = new_twow
        twow_channel.current_twow_id = new_twow.id

    await twow_cmd(
        interaction,
        new_state=TwowState.REGISTERING,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW sign-ups are already open!',
            TwowState.RESPONDING: '🚫 Cannot open sign-ups in the middle of a TWOW season.',
            TwowState.VOTING: '🚫 Cannot open sign-ups in the middle of a TWOW season.',
            TwowState.IDLE: '🚫 Cannot open sign-ups in the middle of a TWOW season.'
        },
        message_content=lambda twow: f'TWOW sign-ups are open! Prompt:\n# {prompt}',
        view_cls=game.signup.SignUpView,
        db_func=db_entry_update
    )


@client.tree.command()
async def prompt(interaction: discord.Interaction, prompt: str):
    """
    Begin a TWOW round.
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
            TwowState.VOTING: '🚫 Voting is open! Please `/conclude` voting before posting a new prompt.',
            TwowState.HIBERNATING: '🚫 No TWOW season. To start a new TWOW season, use `/signup`.'
        },
        message_content=lambda twow: f'Round {twow.current_round} Prompt:\n# {prompt}',
        view_cls=game.prompt.SubmissionView,  # TODO: fix this
        db_func=db_entry_update
    )


@client.tree.command()
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
async def conclude(interaction: discord.Interaction):
    """
    Revert TWOW to idle state.
    """
    async def db_entry_update(session, twow, message):
        twow.current_message_id = message.id
        twow.state = TwowState.IDLE

    await twow_cmd(
        interaction,
        new_state=TwowState.IDLE,
        invalid_entry_dict={
            TwowState.REGISTERING: '🚫 TWOW sign-ups are active! Cannot conclude round until after voting.',
            TwowState.RESPONDING: '🚫 TWOW round is active! Cannot conclude round until after voting.',
            TwowState.IDLE: '🚫 Nothing to conclude? Use `/prompt` to start a TWOW round.',
            TwowState.HIBERNATING: '🚫 Nothing to conclude? Use `/signup` to start a TWOW season.'
        },
        message_content=lambda twow: f'Round {twow.current_round} voting is now closed.',
        view_cls=EmptyView,  # TODO: fix this
        db_func=db_entry_update
    )


@client.tree.command()
async def hibernate(interaction: discord.Interaction):
    """
    Open prompt submission between TWOW seasons.
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


@client.tree.command(name='eval')
async def evaluate(interaction: discord.Interaction, code: str):
    """
    Run python code.
    """
    local_variables = {
        "discord": discord,
        "client": interaction.client,
        "interaction": interaction,
        "channel": interaction.channel,
        "user": interaction.user,
        "guild": interaction.guild,
        "message": interaction.message,
        "db": db,
        "game": game,
    }

    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(
                f"async def func():\n{textwrap.indent(code, '    ')}", local_variables,
            )

            obj = await local_variables["func"]()
            result = f"{stdout.getvalue()}\n-- {obj}\n"
    except Exception as e:
        raise RuntimeError(e)
    
    await interaction.response.send_message(result[0:2000])


@client.tree.command()
async def viewtable(interaction: discord.Interaction, name: str):
    cls = {
        'participant': game.tables.Participant,
        'response': game.tables.Response,
        'vote': game.tables.Vote,
        'twow': Twow,
        'twowchannel': TwowChannel
    }[name]
    async with db.session() as session, session.begin():
        stmt = db.select(cls)
        votes = (await session.scalars(stmt)).all()
    await interaction.response.send_message(str(votes))

client.run(config['discord']['token'])