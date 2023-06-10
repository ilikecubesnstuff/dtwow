from typing import Optional

import discord

# logging setup
import logging
logger = logging.getLogger(__name__)

# project imports
import db
from db import Twow
from .tables import Participant, Response

from utils.views import ConfirmationView, EmptyView


class SubmissionModal(discord.ui.Modal, title='Sign Up'):

    response_input = discord.ui.TextInput(
        label='Response',
        style=discord.TextStyle.long,
        custom_id='registration:response',
        required=True,
        max_length=100
    )

    def __init__(self, twow: Twow, participant: Participant = None, response: Optional[Response] = None):
        super().__init__()

        self.children[0].placeholder = response.content if response else 'Write your 10-word response here!'

        self.twow = twow
        self.participant = participant
        self.response = response or Response(
            twow_id = twow.id,
            user_id = participant.user_id,
            round = twow.current_round
        )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.participant.moniker or interaction.user.name
        async with db.session() as session, session.begin():
            session.add(self.response)
            self.response.content = self.response_input.value.replace('\n', ' ')

        await interaction.response.send_message(f"""Response recorded! ```{name}: "{self.response.content}"```""", ephemeral=True)


class SubmissionView(discord.ui.View):

    def __init__(self, twow):
        super().__init__(timeout=None)
        self.twow = twow

    @discord.ui.button(
        label = 'Submit your response here!',
        row = 0,
        style = discord.ButtonStyle.green,
        custom_id = 'prompt:respond',
    )
    async def submit_response(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            await interaction.response.send_message('You are not signed up to participate in this TWOW season! Make sure to sign up next season.', ephemeral=True)
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)
        if not response:
            modal = SubmissionModal(self.twow, participant=participant)
            await interaction.response.send_modal(modal)
            return

        modal = SubmissionModal(self.twow, participant=participant, response=response)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label = 'View your response.',
        row = 0,
        style = discord.ButtonStyle.gray,
        custom_id = 'prompt:view'
    )
    async def view_response(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            await interaction.response.send_message('You are not signed up to participate in this TWOW season! Make sure to sign up next season.', ephemeral=True)
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)
        if not response:
            await interaction.response.send_message('You have not submitted a response! Click the green button to submit a response.', ephemeral=True)
            return

        name = participant.moniker or interaction.user.name
        await interaction.response.send_message(f'Your response: ```{name}: "{response.content}"```', ephemeral=True)
    
    @discord.ui.button(
        label = 'Delete your response.',
        row = 0,
        style = discord.ButtonStyle.red,
        custom_id = 'prompt:delete'
    )
    async def delete_response(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = await Participant.fetch_by_user(twow_id=self.twow.id, user_id=interaction.user.id)
        if not participant:
            content = f'You are not signed up to participate in this TWOW season! Make sure to sign up next season.'
            await interaction.response.send_message(content, ephemeral=True)
            return

        response = await Response.fetch_by_round_and_user(twow_id=self.twow.id, twow_round=self.twow.current_round, user_id=interaction.user.id)

        content = f'Are you sure? You will not score any points this round unless you submit a response!'
        async def yes(interaction: discord.Interaction):
            async with db.session() as session, session.begin():
                await session.delete(response)
            await interaction.response.edit_message(content='Response deleted.', view=EmptyView(self.twow))
        async def no(interaction: discord.Interaction):
            await interaction.response.edit_message(content='Response preserved.', view=EmptyView(self.twow))
        await interaction.response.send_message(content, view=ConfirmationView(yes, no), ephemeral=True)