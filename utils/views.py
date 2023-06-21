from typing import Coroutine

import discord


class EmptyView(discord.ui.View):
    def __init__(self, twow):
        super().__init__(timeout=None)
        self.twow = twow


class ConfirmationView(discord.ui.View):

    def __init__(self, yes: Coroutine, no: Coroutine):
        super().__init__(timeout=None)
        self._yes = yes
        self._no = no

    @discord.ui.button(
        label='Yes!',
        row = 0,
        style = discord.ButtonStyle.green
    )
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._yes(interaction)

    @discord.ui.button(
        label='No.',
        row = 0,
        style = discord.ButtonStyle.red
    )
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._no(interaction)