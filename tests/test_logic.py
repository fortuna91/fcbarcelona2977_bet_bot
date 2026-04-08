import asyncio
import datetime
from sqlalchemy import select, func
from database import AsyncSessionLocal
from models import Match


async def check():
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.utcnow()
        print(f"Now UTC: {now}")
        
        # Test 1: Daily reminder logic
        stmt1 = select(Match).where(func.date(Match.start_time) == now.date())
        m1 = (await session.execute(stmt1)).scalars().first()
        print(f"Daily match found: {m1.title if m1 else 'None'}")
        
        # Test 2: Hourly reminder logic
        one_hour_later = now + datetime.timedelta(hours=1)
        stmt2 = select(Match).where(Match.start_time > now, Match.start_time <= one_hour_later)
        m2 = (await session.execute(stmt2)).scalars().first()
        print(f"Hourly match found: {m2.title if m2 else 'None'}")
        if m2:
             print(f"Match starts at: {m2.start_time}")

if __name__ == "__main__":
    asyncio.run(check())
