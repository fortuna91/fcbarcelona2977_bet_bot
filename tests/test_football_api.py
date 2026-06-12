from football_api import FootballAPI


def test_fixtures_url_team_mode(monkeypatch):
    monkeypatch.delenv("COMPETITION", raising=False)
    api = FootballAPI()
    assert api._fixtures_url() == "https://api.football-data.org/v4/teams/81/matches"


def test_fixtures_url_competition_mode(monkeypatch):
    monkeypatch.setenv("COMPETITION", "WC")
    api = FootballAPI()
    assert api._fixtures_url() == "https://api.football-data.org/v4/competitions/WC/matches"
