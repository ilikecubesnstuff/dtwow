from typing import Optional, Coroutine

import discord

# logging setup
import logging
logger = logging.getLogger(__name__)

# project imports
import db
from db import Twow
from .tables import Participant, Response

from utils.views import ConfirmationView, EmptyView


class SignUpModal(discord.ui.Modal, title='Sign Up'):

    moniker_input = discord.ui.TextInput(
        label='Moniker',
        style=discord.TextStyle.short,
        custom_id='registration:moniker',
        placeholder='Optional moniker to submit your responses under.',
        required=False,
        max_length=32
    )

    response_input = discord.ui.TextInput(
        label='Response',
        style=discord.TextStyle.long,
        custom_id='registration:response',
        placeholder='Write your 10-word response here!',
        required=True,
        max_length=100
    )

    def __init__(self, twow: Twow, participant: Optional[Participant] = None, response: Optional[Response] = None, user: Optional[discord.User] = None):
        if bool(participant) == bool(user):
            raise ValueError('Must supply one of "participant" or "user" (not both!) to sign-up modal initialization.')
        super().__init__()

        if participant and participant.moniker:
            self.children[0].placeholder = participant.moniker
        if response:
            self.children[1].placeholder = response.content
            self.children[1].required = False

        self.twow = twow
        self.participant = participant or Participant(
            twow_id = twow.id,
            user_id = user.id
        )
        self.response = response or Response(
            twow_id = twow.id,
            user_id = user.id,
            round = twow.current_round
        )

    async def on_submit(self, interaction: discord.Interaction):
        async with db.session() as session, session.begin():
            session.add(self.participant)
            if self.moniker_input.value:
                self.participant.moniker = self.moniker_input.value.replace('\n', ' ')

            session.add(self.response)
            if self.response_input.value:
                self.response.content = self.response_input.value.replace('\n', ' ')

        await interaction.response.send_message(f"""Response recorded! ```{self.participant.moniker}: "{self.response.content}"```""", ephemeral=True)


class SignUpView(discord.ui.View):

    def __init__(self, twow: Twow):
        super().__init__(timeout=None)
        self.twow = twow

    @discord.ui.button(
        label = 'Sign up for TWOW here.',
        row = 0,
        style = discord.ButtonStyle.green,
        custom_id = 'signup:register',
    )
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            modal = SignUpModal(self.twow, user=interaction.user)
            await interaction.response.send_modal(modal)
            logger.info('No participant record, modal sent.')
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)
        if not response:
            modal = SignUpModal(self.twow, participant=participant)
            await interaction.response.send_modal(modal)
            return

        modal = SignUpModal(self.twow, participant=participant, response=response)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label = 'View your response.',
        row = 0,
        style = discord.ButtonStyle.gray,
        custom_id = 'signup:view_response'
    )
    async def view_response(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            await interaction.response.send_message('You are not signed up! Click the green button to submit (an optional moniker and) a response.', ephemeral=True)
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)
        if not response:
            await interaction.response.send_message('You are not signed up! Click the green button to submit a response.', ephemeral=True)
            return

        name = participant.moniker or interaction.user.name
        await interaction.response.send_message(f'Your response: ```{name}: "{response.content}"```', ephemeral=True)
    
    @discord.ui.button(
        label = 'Reset moniker.',
        row = 1,
        style = discord.ButtonStyle.red,
        custom_id = 'signup:reset_moniker'
    )
    async def reset_moniker(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            content = f'You are not signed up! Click the green button to submit (an optional moniker and) a response.'
            await interaction.response.send_message(content, ephemeral=True)
            return
        if not participant.moniker:
            content = f'You have no moniker set! (Your responses will show up under `{interaction.user.name}`.)'
            await interaction.response.send_message(content, ephemeral=True)
            return

        content = f'Are you sure? Your responses will show up under `{interaction.user.name}`.'
        async def yes(interaction: discord.Interaction):
            async with db.session() as session, session.begin():
                session.add(participant)
                participant.moniker = None
            await interaction.response.edit_message(content='Moniker reset.', view=EmptyView(self.twow))
        async def no(interaction: discord.Interaction):
            await interaction.response.edit_message(content='Moniker preserved.', view=EmptyView(self.twow))
        await interaction.response.send_message(content, view=ConfirmationView(yes, no), ephemeral=True)
    
    @discord.ui.button(
        label = 'Remove me from TWOW!',
        row = 1,
        style = discord.ButtonStyle.red,
        custom_id = 'signup:remove_user'
    )
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            content = f'You are not signed up! Click the green button to submit (an optional moniker and) a response.'
            await interaction.response.send_message(content, ephemeral=True)
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)

        content = f'Are you sure? You will not be able to participate for the entire TWOW season.'
        async def yes(interaction: discord.Interaction):
            async with db.session() as session, session.begin():
                await session.delete(participant)
                await session.delete(response)
            await interaction.response.edit_message(content='You have been removed from this TWOW season.', view=EmptyView(self.twow))
        async def no(interaction: discord.Interaction):
            await interaction.response.edit_message(content='Action cancelled.', view=EmptyView(self.twow))
        await interaction.response.send_message(content, view=ConfirmationView(yes, no), ephemeral=True)
