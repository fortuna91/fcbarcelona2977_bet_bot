import os
import httpx
import datetime
from dotenv import load_dotenv

load_dotenv()

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
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get('response', [])

    async def get_fixture_by_id(self, fixture_id: int):
        """Fetch details for a specific match to check the score."""
        url = f"{self.base_url}/fixtures"
        params = {"id": fixture_id}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            res = response.json().get('response', [])
            return res[0] if res else None
