import datetime
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Cascade delete ensures that deleting a user removes all their bets
    bets = relationship("Bet", back_populates="user", cascade="all, delete-orphan")

class Match(Base):
    __tablename__ = 'matches'
    id = Column(Integer, primary_key=True) # API-Football Fixture ID
    title = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    actual_home_score = Column(Integer, nullable=True)
    actual_guest_score = Column(Integer, nullable=True)
    status = Column(String, default="NS") # NS: Not Started, FT: Finished
    
    bets = relationship("Bet", back_populates="match", cascade="all, delete-orphan")

class Bet(Base):
    __tablename__ = 'bets'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    match_id = Column(Integer, ForeignKey('matches.id', ondelete="CASCADE"), nullable=False)
    bet_home_score = Column(Integer, nullable=False)
    bet_guest_score = Column(Integer, nullable=False)
    points_earned = Column(Integer, default=0)
    
    user = relationship("User", back_populates="bets")
    match = relationship("Match", back_populates="bets")

    __table_args__ = (UniqueConstraint('user_id', 'match_id', name='_user_match_uc'),)
