from collections import Counter
import random

import discord

# logging setup
import logging
logger = logging.getLogger(__name__)

# project imports
import db
from db import Twow
from .tables import Participant, Response, Vote

from utils.views import EmptyView


async def formatted_options(interaction: discord.Interaction, twow: Twow, vote_count = 0):
    async with db.session() as session, session.begin():
        stmt = db.select(Response).where(
            Response.twow_id == twow.id,
            Response.round == twow.current_round,
            Response.user_id != interaction.user.id
        )
        responses = (await session.scalars(stmt)).all()

        stmt = db.select(Vote).where(
            Vote.twow_id == twow.id,
            Vote.round == twow.current_round,
            Vote.user_id == interaction.user.id
        )
        votes = (await session.scalars(stmt)).all()

    if len(responses) < 2:
        return 'Not enough responses!', EmptyView(twow)

    vote_pairs = [(vote.upvoted_id, vote.downvoted_id) for vote in votes]
    c = Counter({response.id: 0 for response in responses})
    c.update(sum(vote_pairs, ()))  # flattened vote_pairs

    freqs = c.most_common()
    _, lowest = freqs[-1]
    pool = [response for response, freq in freqs if freq == lowest]
    r1 = random.choice(pool)

    pool = [response for response in responses if any(response in pair and r1 in pair for pair in vote_pairs)]
    r2 = random.choice(pool)

    if random.random() < 0.5:
        r2, r1 = r1, r2

    vote_chip = f' [{vote_count} recorded vote(s)]' if vote_count else ''
    content = f"Which response do you prefer?{vote_chip}\n**Option 1** - `{r1.content}`\n**Option 2** - `{r2.content}`"
    view = ParticipantVoteView(twow, r1, r2, count=vote_count + 1)
    return content, view


async def handle_user_vote():
    pass



class ParticipantVoteView(discord.ui.View):

    def __init__(self, twow: Twow, left: Response, right: Response, count: int = 0):
        super().__init__(timeout=None)
        self.twow: Twow = twow
        self.left: Response = left
        self.right: Response = right
        self.count: int = count

    @discord.ui.button(
        label='Option 1',
        style=discord.ButtonStyle.blurple,
        custom_id='vote:left'
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_vote = Vote(
            twow_id=self.twow.id,
            user_id=interaction.user.id,
            round=self.twow.current_round,
            upvoted_id=self.left.id,
            downvoted_id=self.right.id
        )
        async with db.session() as session, session.begin():
            session.add(user_vote)

        content, view = await formatted_options(interaction, self.twow, self.count)
        await interaction.response.edit_message(content=content, view=view)

    @discord.ui.button(
        label='Option 2',
        style=discord.ButtonStyle.blurple,
        custom_id='vote:right'
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_vote = Vote(
            twow_id=self.twow.id,
            user_id=interaction.user.id,
            round=self.twow.current_round,
            upvoted_id=self.right.id,
            downvoted_id=self.left.id
        )
        async with db.session() as session, session.begin():
            session.add(user_vote)

        content, view = await formatted_options(interaction, self.twow, self.count)
        await interaction.response.edit_message(content=content, view=view)


class VotingView(discord.ui.View):

    def __init__(self, twow: Twow):
        super().__init__(timeout=None)
        self.twow = twow
    
    @discord.ui.button(
        label='Vote here!',
        row = 0,
        style = discord.ButtonStyle.green,
        custom_id='voting:vote'
    )
    async def start_voting(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with db.session() as session, session.begin():
            stmt = db.select(Vote).where(
                Vote.twow_id == self.twow.id,
                Vote.round == self.twow.current_round,
                Vote.user_id == interaction.user.id
            )
            votes = (await session.scalars(stmt)).all()
        content, view = await formatted_options(interaction, self.twow, vote_count=len(votes))
        await interaction.response.send_message(content, view=view, ephemeral=True)
