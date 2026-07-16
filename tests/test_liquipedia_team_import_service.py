from cs2eye.services.liquipedia_team_import_service import (
    parse_liquipedia_team_roster_html,
)


def test_inactive_roster_is_not_parsed_as_active() -> None:
    html = """
    <h2>Player Roster</h2>

    <h3>Active</h3>
    <table>
      <tr>
        <td>
          <a href="/counterstrike/player1">
            player1
          </a>
        </td>
      </tr>
      <tr>
        <td>
          <a href="/counterstrike/player2">
            player2
          </a>
        </td>
      </tr>
      <tr>
        <td>
          <a href="/counterstrike/player3">
            player3
          </a>
        </td>
      </tr>
      <tr>
        <td>
          <a href="/counterstrike/player4">
            player4
          </a>
        </td>
      </tr>
      <tr>
        <td>
          <a href="/counterstrike/player5">
            player5
          </a>
        </td>
      </tr>
    </table>

    <h3>Inactive</h3>
    <table>
      <tr>
        <td>
          <a href="/counterstrike/chopper">
            chopper
          </a>
        </td>
        <td>2025-12-18</td>
      </tr>
    </table>
    """

    draft = parse_liquipedia_team_roster_html(
        team_name="Team Spirit",
        page_name="Team_Spirit",
        html=html,
    )

    active_nicknames = {
        player.nickname
        for player in draft.players
        if player.status == "active"
    }

    assert active_nicknames == {
        "player1",
        "player2",
        "player3",
        "player4",
        "player5",
    }

    assert "chopper" not in active_nicknames