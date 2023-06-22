from collections import Counter, defaultdict

import discord

# logging setup
import logging
logger = logging.getLogger(__name__)

# project imports
import db
from db import Twow
from .tables import Participant, Response, Vote

from utils.misc import clumped


async def update(twow: Twow):
    async with db.session() as session, session.begin():

    # update ratings
        stmt = db.select(Participant).where(
            Participant.twow_id == twow.id
        )
        participants = (await session.scalars(stmt)).all()

        stmt = db.select(Response).where(
            Response.twow_id == twow.id,
            Response.round == twow.current_round
        )
        responses = (await session.scalars(stmt)).all()

        stmt = db.select(Vote).where(
            Vote.twow_id == twow.id,
            Vote.round == twow.current_round
        )
        votes = (await session.scalars(stmt)).all()

    if not votes:
        return

    responses = {response.id: response for response in responses}
    for participant in participants:
        voted_response_ids = [(vote.upvoted_id, vote.downvoted_id) for vote in votes if vote.user_id == participant.user_id]
        c = Counter(sum(voted_response_ids, ()))
        for upvoted_id, downvoted_id in voted_response_ids:
            upvoted = responses[upvoted_id]
            downvoted = responses[downvoted_id]
            w1 = 1/c[upvoted_id]
            w2 = 1/c[downvoted_id]
            await Response.update_ratings(upvoted=upvoted, downvoted=downvoted, weights=(w1, w2))

    # update scores
    QUANTILE = 6 if twow.current_round != 7 else 3
    NO_SCORE = 1 if twow.current_round != 7 else 0
    async with db.session() as session, session.begin():
        stmt = db.select(Participant).where(
            Participant.twow_id == twow.id
        )
        participants = (await session.scalars(stmt)).all()

        stmt = db.select(Response).where(
            Response.twow_id == twow.id,
            Response.round == twow.current_round
        )
        responses = (await session.scalars(stmt)).all()

        session.add_all(responses)
        step = len(responses)//QUANTILE  # ib scoring system
        round_score = defaultdict(lambda: NO_SCORE)
        for i, response in enumerate(sorted(responses, key=lambda r: r.rating)):
            score = NO_SCORE + (i//step if step else 0)
            response.score = score
            round_score[response.user_id] = score

        if twow.current_round > 0:
            session.add_all(participants)
            for participant in participants:
                participant.score += round_score[participant.user_id]
        

async def display(twow: Twow, thread: discord.Thread):
    async with db.session() as session:
        stmt = db.select(Participant).where(
            Participant.twow_id == twow.id
        )
        participants = (await session.scalars(stmt)).all()

        stmt = db.select(Response).where(
            Response.twow_id == twow.id,
            Response.round == twow.current_round
        )
        responses = (await session.scalars(stmt)).all()

    for participant in participants:
        if not participant.moniker:
            try:
                participant.moniker = (await thread.guild.fetch_member(participant.user_id)).display_name
            except discord.Forbidden:
                logger.warning(f'I do not have access to the guild.')
                return 'I do not have access to the guild..'
            except discord.NotFound:
                logger.warning(f'A member with ID {participant.user_id} could not be found.')
                participant.moniker = '???'
            except discord.HTTPException:
                logger.warning(f'Fetching member with ID {participant.user_id} failed.')
                return 'HTTP Exception occurred.'

    PAGE_SIZE = 3
    for clump in clumped(enumerate(sorted(responses, key=lambda r: r.rating, reverse=True), start=1), n=PAGE_SIZE):
        embed = discord.Embed()
        for rank, response in clump:
            participant ,= [p for p in participants if p.user_id == response.user_id]
            embed.add_field(
                name = f"{rank}. {response.content} ({len(response.content.split())} words)",
                value = f"{round(response.rating)} ELO ({response.upvotes}/{response.downvotes}) - by **{participant.moniker}**, {response.score} points ({participant.score} total)",
                inline = False
            )
        await thread.send(embed=embed)
    return 'Results sent!'