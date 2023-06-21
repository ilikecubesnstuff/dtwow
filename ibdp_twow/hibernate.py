from typing import Optional, Coroutine

import discord

# logging setup
import logging
logger = logging.getLogger(__name__)

# project imports
import db
from db import Prompt, Twow, TwowChannel
from .tables import Participant, Response

from utils.views import ConfirmationView, EmptyView


class PromptSubmissionModal(discord.ui.Modal, title='Suggesting a Prompt'):

    prompt_input = discord.ui.TextInput(
        label='Prompt',
        style=discord.TextStyle.long,
        custom_id='promptsubmission:prompt',
        placeholder='Write your prompt here!',
        required=True,
        max_length=200
    )

    def __init__(self, twow: Twow):
        super().__init__()
        self.twow = twow

    async def on_submit(self, interaction: discord.Interaction):
        prompt = Prompt(
            user_id = interaction.user.id,
            content = self.prompt_input.value
        )
        async with db.session() as session, session.begin():
            session.add(prompt)

        if not self.twow.private_channel_id:
            private_channel = await interaction.channel.create_thread(name=f"TWOW Host Thread ({self.twow.id})")
            async with db.session() as session, session.begin():
                session.add(self.twow)
                self.twow.private_channel_id = private_channel.id
        else:
            private_channel = interaction.guild.get_channel_or_thread(self.twow.private_channel_id)
        await private_channel.send(f'Prompt submitted by {interaction.user.mention}: "{prompt.content}"')

        await interaction.response.send_message(f"""Thank you! ```Prompt submitted: "{prompt.content}"```""", ephemeral=True)


class FeedbackModal(discord.ui.Modal, title='Feedback'):

    feedback_input = discord.ui.TextInput(
        label='Feedback',
        style=discord.TextStyle.long,
        custom_id='feedback:feedback',
        placeholder='Write your feedback here!',
        required=True
    )

    def __init__(self, twow: Twow):
        super().__init__()
        self.twow = twow

    async def on_submit(self, interaction: discord.Interaction):
        if not self.twow.private_channel_id:
            private_channel = await interaction.channel.create_thread(f"TWOW Host Thread ({self.twow.id})")
            async with db.session() as session, session.begin():
                session.add(self.twow)
                self.twow.private_channel_id = private_channel.id

                host_id = await session.get(TwowChannel, self.twow.channel_id).host_id
            if host_id:
                await private_channel.send(f'<@&{host_id}>')
        else:
            private_channel = interaction.guild.get_channel_or_thread(self.twow.private_channel_id)
        await private_channel.send(f'Feedback submitted by {interaction.user.mention}: "{self.feedback_input.value}"')

        await interaction.response.send_message(f"""Thank you! ```Feedback submitted: "{self.feedback_input.value}"```""", ephemeral=True)


class HibernationView(discord.ui.View):

    def __init__(self, twow: Twow):
        super().__init__(timeout=None)
        self.twow = twow

    @discord.ui.button(
        label = 'Submit your own prompts!',
        row = 0,
        style = discord.ButtonStyle.green,
        custom_id = 'hibernation:promptsubmission',
    )
    async def submit_prompt(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PromptSubmissionModal(self.twow)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label = 'Give us feedback!',
        row = 0,
        style = discord.ButtonStyle.blurple,
        custom_id = 'hibernation:feedback',
    )
    async def give_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FeedbackModal(self.twow)
        await interaction.response.send_modal(modal)
