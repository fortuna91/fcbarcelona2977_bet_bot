import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class FootballAPI:
    def __init__(self):
        # We use the same env variable name but now it expects a football-data.org token
        self.api_key = os.getenv("FOOTBALL_API_KEY")
        self.base_url = "https://api.football-data.org/v4"
        self.headers = {
            "X-Auth-Token": self.api_key
        }
        self.team_id = 86 # FC Barcelona ID in football-data.org

    async def get_fixtures(self):
        """Fetch all FC Barcelona matches for the current season."""
        url = f"{self.base_url}/teams/{self.team_id}/matches"
        
        logger.info(f"Requesting matches for team {self.team_id} from football-data.org...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                results = data.get('matches', [])
                logger.info(f"Successfully fetched {len(results)} matches.")
                return results
            except Exception as e:
                logger.error(f"Failed to fetch matches: {e}")
                if hasattr(e, 'response') and e.response:
                    logger.error(f"Response: {e.response.text}")
                return []

    async def get_fixture_by_id(self, fixture_id: int):
        """Fetch details for a specific match to check the score."""
        url = f"{self.base_url}/matches/{fixture_id}"
        
        logger.info(f"Requesting details for match ID: {fixture_id}...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                if data:
                    logger.info(f"Successfully fetched details for match {fixture_id}.")
                    return data
                else:
                    logger.warning(f"No data found for match {fixture_id}.")
                    return None
            except Exception as e:
                logger.error(f"Failed to fetch match {fixture_id}: {e}")
                return None
