import math
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel

class MatchId(BaseModel):
    s: int  # Section (1: WB, 2: LB)
    r: int  # Round
    m: int  # Match index

    def __str__(self):
        bracket = "WB" if self.s == 1 else "LB"
        return f"{bracket} R{self.r} M{self.m}"

class Match(BaseModel):
    id: MatchId
    p: List[int]  # Player seeds or IDs (0: None, -1: Walkover)
    m: Optional[List[float]] = None  # Scores
    scorable: bool = True

class TournamentEngine:
    def __init__(self, name: str, num_players: int):
        self.name = name
        self.num_players = num_players
        self.matches: List[Match] = []

    def find_match(self, match_id: MatchId) -> Optional[Match]:
        for m in self.matches:
            if m.id.s == match_id.s and m.id.r == match_id.r and m.id.m == match_id.m:
                return m
        return None

class Duel(TournamentEngine):
    WB = 1
    LB = 2
    WO = -1
    NONE = 0

    def __init__(self, num_players: int, double_elim: bool = False):
        super().__init__("Duel", num_players)
        self.double_elim = double_elim
        self.p = math.ceil(math.log2(num_players))
        self._create_matches()

    def _create_matches(self):
        # 1. Winners Bracket — all rounds
        for r in range(1, self.p + 1):
            num_matches = 2**(self.p - r)
            for i in range(1, num_matches + 1):
                self.matches.append(Match(id=MatchId(s=self.WB, r=r, m=i), p=[0, 0]))

        # 2. Losers Bracket (if double elimination)
        # Standard structure: 2*(p-1) rounds
        # Odd rounds (1,3,5,...): receive WB dropdowns (same #matches as previous LB round or WB)
        # Even rounds (2,4,6,...): internal LB halving
        if self.double_elim and self.p >= 2:
            lb_rounds = 2 * (self.p - 1)
            for lr in range(1, lb_rounds + 1):
                if lr == 1:
                    # First LB round: WB R1 losers play each other
                    num = 2**(self.p - 2)
                elif lr % 2 == 0:
                    # Even round: same count as previous odd round (halved from WB dropdowns)
                    num = prev_count
                else:
                    # Odd round (>1): receives WB dropdowns, half of previous
                    num = max(1, prev_count // 2)
                prev_count = num
                for i in range(1, num + 1):
                    self.matches.append(Match(id=MatchId(s=self.LB, r=lr, m=i), p=[0, 0]))
            
            # Grand Final in WB (last WB round + 1) — oozturn style
            self.matches.append(Match(id=MatchId(s=self.WB, r=self.p + 1, m=1), p=[0, 0]))

    def score(self, match_id: MatchId, scores: List[float]):
        match = self.find_match(match_id)
        if not match:
            return
        match.m = scores
        self._progress(match)

    def _progress(self, match: Match):
        # Basic progression logic (to be refined based on tournament-js)
        winner_idx = 0 if match.m[0] > match.m[1] else 1
        loser_idx = 1 - winner_idx
        
        winner = match.p[winner_idx]
        loser = match.p[loser_idx]

        # Progress winner in WB
        if match.id.s == self.WB:
            if match.id.r < self.p:
                next_match_id = MatchId(s=self.WB, r=match.id.r + 1, m=(match.id.m + 1) // 2)
                next_match = self.find_match(next_match_id)
                if next_match:
                    next_match.p[(match.id.m - 1) % 2] = winner
            elif self.double_elim:
                # To LB Grand Final
                gf_id = MatchId(s=self.LB, r=2 * self.p - 1, m=1)
                gf = self.find_match(gf_id)
                if gf:
                    gf.p[0] = winner

        # Progress loser to LB if double elim
        if self.double_elim and match.id.s == self.WB:
            # Loser drops to LB
            lb_round = (match.id.r - 1) * 2 if match.id.r > 1 else 1
            lb_id = MatchId(s=self.LB, r=lb_round, m=match.id.m)
            lb_match = self.find_match(lb_id)
            if lb_match:
                lb_match.p[0] = loser


class RoundRobin(TournamentEngine):
    """Round-robin tournament: every participant plays every other participant once."""
    
    def __init__(self, num_players: int):
        super().__init__("RoundRobin", num_players)
        self._create_matches()
    
    def _create_matches(self):
        """Circle method for round-robin scheduling."""
        n = self.num_players
        if n < 2:
            return
        
        # If odd number, add a phantom player (bye)
        players = list(range(1, n + 1))
        if n % 2 == 1:
            players.append(0)  # 0 = bye
        
        num_rounds = len(players) - 1
        half = len(players) // 2
        
        for r in range(1, num_rounds + 1):
            match_idx = 0
            for i in range(half):
                p1 = players[i]
                p2 = players[len(players) - 1 - i]
                # Skip byes
                if p1 == 0 or p2 == 0:
                    continue
                match_idx += 1
                self.matches.append(Match(
                    id=MatchId(s=1, r=r, m=match_idx),
                    p=[p1, p2]
                ))
            # Rotate: fix first player, rotate rest
            players = [players[0]] + [players[-1]] + players[1:-1]


class FFA(TournamentEngine):
    """Free-For-All tournament: all players compete in a single match per round.
    Score is a ranking (placement). Admin creates subsequent rounds with top N players."""
    
    def __init__(self, num_players: int):
        super().__init__("FFA", num_players)
        # Create round 1 with all players
        self.matches.append(Match(
            id=MatchId(s=1, r=1, m=1),
            p=list(range(1, num_players + 1))
        ))
