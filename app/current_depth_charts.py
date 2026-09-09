"""
Manually researched, current (as of Sept 2026) skill-position starters for
all 32 teams -- RB1, WR1, WR2, TE1. This REPLACES the automated "most-used
player last season" approach in app/player_props.py's get_skill_players()
with real, individually-checked current depth charts (source: RotoWire +
LeagueStation team depth chart pages, cross-checked against nflverse's
2025 player stats to classify each player).

Classification, per the request that produced this file:
  - "rookie": True  -> player has no 2025 NFL stats at all (rookie or
    otherwise unproven at the NFL level). No stat line is shown for these
    players; the site should just display "Rookie."
  - "new_team": <old team abbr> -> player has real 2025 stats, but with a
    DIFFERENT team than the one they're listed with now (trade/free
    agency). Their 2025 stats are still used, with a note about the team
    change.
  - Neither field present -> same team as 2025, stats used normally.

This is real research, not the trailing-usage automation -- but it is a
snapshot as of when it was built. Depth charts shift constantly (injuries,
performance, coaching decisions); treat this the same way qb_meta.py is
treated: a real starting point that benefits from periodic manual review,
not a permanently-correct source of truth.
"""

DEPTH_CHART = {
    "ARI": {"rb1": "Jeremiyah Love", "wr1": "Marvin Harrison Jr.", "wr2": "Michael Wilson", "te1": "Trey McBride"},
    "ATL": {"rb1": "Bijan Robinson", "wr1": "Drake London", "wr2": "Zachariah Branch", "te1": "Kyle Pitts"},
    "BAL": {"rb1": "Derrick Henry", "wr1": "Zay Flowers", "wr2": "Rashod Bateman", "te1": "Mark Andrews"},
    "BUF": {"rb1": "James Cook", "wr1": "DJ Moore", "wr2": "Khalil Shakir", "te1": "Dalton Kincaid"},
    "CAR": {"rb1": "Jonathon Brooks", "wr1": "Tetairoa McMillan", "wr2": "Jalen Coker", "te1": "Darren Waller"},
    "CHI": {"rb1": "D'Andre Swift", "wr1": "Luther Burden", "wr2": "Rome Odunze", "te1": "Colston Loveland"},
    "CIN": {"rb1": "Chase Brown", "wr1": "Ja'Marr Chase", "wr2": "Tee Higgins", "te1": "Mike Gesicki"},
    "CLE": {"rb1": "Quinshon Judkins", "wr1": "KC Concepcion", "wr2": "Denzel Boston", "te1": "Harold Fannin"},
    "DAL": {"rb1": "Javonte Williams", "wr1": "CeeDee Lamb", "wr2": "George Pickens", "te1": "Jake Ferguson"},
    "DEN": {"rb1": "J.K. Dobbins", "wr1": "Jaylen Waddle", "wr2": "Courtland Sutton", "te1": "Evan Engram"},
    "DET": {"rb1": "Jahmyr Gibbs", "wr1": "Amon-Ra St. Brown", "wr2": "Jameson Williams", "te1": "Sam LaPorta"},
    "GB": {"rb1": "MarShawn Lloyd", "wr1": "Christian Watson", "wr2": "Jayden Reed", "te1": "Tucker Kraft"},
    "HOU": {"rb1": "David Montgomery", "wr1": "Nico Collins", "wr2": "Kayshon Boutte", "te1": "Dalton Schultz"},
    "IND": {"rb1": "Jonathan Taylor", "wr1": "Alec Pierce", "wr2": "Josh Downs", "te1": "Tyler Warren"},
    "JAX": {"rb1": "Bhayshul Tuten", "wr1": "Parker Washington", "wr2": "Brian Thomas Jr.", "te1": "Brenton Strange"},
    "KC": {"rb1": "Kenneth Walker III", "wr1": "Rashee Rice", "wr2": "Xavier Worthy", "te1": "Travis Kelce"},
    "LAC": {"rb1": "Omarion Hampton", "wr1": "Ladd McConkey", "wr2": "Quentin Johnston", "te1": "Oronde Gadsden II"},
    "LA": {"rb1": "Kyren Williams", "wr1": "Puka Nacua", "wr2": "Davante Adams", "te1": "Terrance Ferguson"},
    "LV": {"rb1": "Ashton Jeanty", "wr1": "Tre Tucker", "wr2": "Jalen Nailor", "te1": "Brock Bowers"},
    "MIA": {"rb1": "De'Von Achane", "wr1": "Malik Washington", "wr2": "Chris Bell", "te1": "Greg Dulcich"},
    "MIN": {"rb1": "Jordan Mason", "wr1": "Justin Jefferson", "wr2": "Jordan Addison", "te1": "T.J. Hockenson"},
    "NE": {"rb1": "TreVeyon Henderson", "wr1": "A.J. Brown", "wr2": "Romeo Doubs", "te1": "Hunter Henry"},
    "NO": {"rb1": "Travis Etienne Jr.", "wr1": "Chris Olave", "wr2": "Jordyn Tyson", "te1": "Juwan Johnson"},
    "NYG": {"rb1": "Cam Skattebo", "wr1": "Malik Nabers", "wr2": "Darnell Mooney", "te1": "Isaiah Likely"},
    "NYJ": {"rb1": "Breece Hall", "wr1": "Garrett Wilson", "wr2": "Adonai Mitchell", "te1": "Kenyon Sadiq"},
    "PHI": {"rb1": "Saquon Barkley", "wr1": "DeVonta Smith", "wr2": "Makai Lemon", "te1": "Dallas Goedert"},
    "PIT": {"rb1": "Jaylen Warren", "wr1": "DK Metcalf", "wr2": "Michael Pittman Jr.", "te1": "Pat Freiermuth"},
    "SEA": {"rb1": "Jadarian Price", "wr1": "Jaxon Smith-Njigba", "wr2": "Rashid Shaheed", "te1": "AJ Barner"},
    "SF": {"rb1": "Christian McCaffrey", "wr1": "Mike Evans", "wr2": "De'Zhaun Stribling", "te1": "George Kittle"},
    "TB": {"rb1": "Bucky Irving", "wr1": "Emeka Egbuka", "wr2": "Chris Godwin", "te1": "Cade Otton"},
    "TEN": {"rb1": "Tony Pollard", "wr1": "Carnell Tate", "wr2": "Wan'Dale Robinson", "te1": "Gunnar Helm"},
    "WAS": {"rb1": "Jacory Croskey-Merritt", "wr1": "Terry McLaurin", "wr2": "Stefon Diggs", "te1": "Chig Okonkwo"},
}
