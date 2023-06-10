import db
from db import Base, mapped_column
from db import Integer, String, Float, ForeignKey


class Participant(Base):
    __tablename__ = "ib_participants"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    twow_id = mapped_column(ForeignKey('twows.id'))
    user_id = mapped_column(Integer)
    moniker = mapped_column(String(32), nullable=True)
    score = mapped_column(Integer, default=0)

    @classmethod
    async def fetch_by_user(cls, *, twow_id, user_id):
        async with db.session() as session:
            stmt = db.select(cls).where(
                cls.twow_id == twow_id,
                cls.user_id == user_id
            )
            participant = (await session.scalars(stmt)).one_or_none()
        return participant


class Response(Base):
    __tablename__ = "ib_responses"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    twow_id = mapped_column(ForeignKey('twows.id'))
    user_id = mapped_column(Integer)
    round = mapped_column(Integer)
    content = mapped_column(String, nullable=True)
    rating = mapped_column(Float, default=1000.)

    @classmethod
    async def fetch_by_round_and_user(cls, *, twow_id, twow_round, user_id):
        async with db.session() as session:
            stmt = db.select(cls).where(
                cls.twow_id == twow_id,
                cls.user_id == user_id,
                cls.round == twow_round
            )
            participant = (await session.scalars(stmt)).one_or_none()
        return participant

    @classmethod
    async def update_ratings(cls, *, upvoted, downvoted, weights: tuple[int] = (1, 1)):
        w1, w2 = weights
        rating_difference = upvoted.rating - downvoted.rating
        expected_value = 1 / (1 + 10 ** (rating_difference / 400))  # adapted from https://en.wikipedia.org/wiki/Elo_rating_system
        async with db.session() as session, session.begin():
            session.add_all([upvoted, downvoted])
            upvoted.rating += 50 * expected_value * w1
            downvoted.rating -= 50 * expected_value * w2


class Vote(Base):
    __tablename__ = "ib_votes"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    twow_id = mapped_column(ForeignKey('twows.id'))
    user_id = mapped_column(Integer)
    round = mapped_column(Integer)
    upvoted_id = mapped_column(ForeignKey('ib_responses.id'))
    downvoted_id = mapped_column(ForeignKey('ib_responses.id'))
