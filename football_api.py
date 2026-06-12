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
        self.headers = {"X-Auth-Token": self.api_key}
        self.team_id = 81  # FC Barcelona ID in football-data.org
        # When set (e.g. "WC"), fetch a whole competition instead of one team's matches.
        self.competition = os.getenv("COMPETITION")

    async def _make_request(self, url):
        """Internal helper for API requests with common error handling."""
        logger.debug(f"Requesting URL: {url}")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Failed to fetch data from {url}: {e}")
                if hasattr(e, "response") and e.response:
                    logger.error(f"Response: {e.response.text}")
                return None

    def _fixtures_url(self) -> str:
        """Builds the fixtures URL: a competition's matches if COMPETITION is set, else the team's."""
        if self.competition:
            return f"{self.base_url}/competitions/{self.competition}/matches"
        return f"{self.base_url}/teams/{self.team_id}/matches"

    async def get_fixtures(self):
        """Fetch all matches for the configured competition (or FC Barcelona by default)."""
        url = self._fixtures_url()
        logger.info(f"Requesting fixtures from {url}")
        data = await self._make_request(url)
        if data:
            results = data.get("matches", [])
            logger.info(f"Successfully fetched {len(results)} matches.")
            return results
        return []

    async def get_fixture_by_id(self, fixture_id: int):
        """Fetch details for a specific match to check the score."""
        url = f"{self.base_url}/matches/{fixture_id}"
        logger.info(f"Requesting details for match ID: {fixture_id}...")
        return await self._make_request(url)
