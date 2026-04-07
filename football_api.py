import os
import httpx
import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class FootballAPI:
    def __init__(self):
        self.api_key = os.getenv("FOOTBALL_API_KEY")
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            "x-apisports-key": self.api_key
        }
        self.team_id = 529 # FC Barcelona

    async def get_fixtures(self, season: int = 2025):
        """Fetch all FC Barcelona fixtures for the season."""
        url = f"{self.base_url}/fixtures"
        params = {"team": self.team_id, "season": season}
        
        logger.info(f"Requesting fixtures for team {self.team_id}, season {season}...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get('response', [])
                logger.info(f"Successfully fetched {len(results)} fixtures.")
                return results
            except Exception as e:
                logger.error(f"Failed to fetch fixtures: {e}")
                return []

    async def get_fixture_by_id(self, fixture_id: int):
        """Fetch details for a specific match to check the score."""
        url = f"{self.base_url}/fixtures"
        params = {"id": fixture_id}
        
        logger.info(f"Requesting details for fixture ID: {fixture_id}...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                res = data.get('response', [])
                if res:
                    logger.info(f"Successfully fetched details for fixture {fixture_id}.")
                    return res[0]
                else:
                    logger.warning(f"No data found for fixture {fixture_id}.")
                    return None
            except Exception as e:
                logger.error(f"Failed to fetch fixture {fixture_id}: {e}")
                return None
