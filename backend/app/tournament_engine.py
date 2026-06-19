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
    def __init__(self, name: str, num_players: int, config: Dict[str, Any] = None):
        self.name = name
        self.num_players = num_players
        self.config = config or {}
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

    def __init__(self, num_players: int, double_elim: bool = False, config: Dict[str, Any] = None):
        super().__init__("Duel", num_players, config)
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
        if self.double_elim and self.p >= 2:
            lb_rounds = 2 * (self.p - 1)
            for lr in range(1, lb_rounds + 1):
                if lr == 1:
                    num = 2**(self.p - 2)
                elif lr % 2 == 0:
                    num = prev_count
                else:
                    num = max(1, prev_count // 2)
                prev_count = num
                for i in range(1, num + 1):
                    self.matches.append(Match(id=MatchId(s=self.LB, r=lr, m=i), p=[0, 0]))
            
            # Grand Final in WB (last WB round + 1)
            self.matches.append(Match(id=MatchId(s=self.WB, r=self.p + 1, m=1), p=[0, 0]))

    def score(self, match_id: MatchId, scores: List[float]):
        match = self.find_match(match_id)
        if not match:
            return
        match.m = scores
        self._progress(match)

    def _progress(self, match: Match):
        winner_idx = 0 if match.m[0] > match.m[1] else 1
        loser_idx = 1 - winner_idx
        
        winner = match.p[winner_idx]
        loser = match.p[loser_idx]

        if match.id.s == self.WB:
            if match.id.r < self.p:
                next_match_id = MatchId(s=self.WB, r=match.id.r + 1, m=(match.id.m + 1) // 2)
                next_match = self.find_match(next_match_id)
                if next_match:
                    next_match.p[(match.id.m - 1) % 2] = winner
            elif self.double_elim:
                gf_id = MatchId(s=self.LB, r=2 * self.p - 1, m=1)
                gf = self.find_match(gf_id)
                if gf:
                    gf.p[0] = winner

        if self.double_elim and match.id.s == self.WB:
            lb_round = (match.id.r - 1) * 2 if match.id.r > 1 else 1
            lb_id = MatchId(s=self.LB, r=lb_round, m=match.id.m)
            lb_match = self.find_match(lb_id)
            if lb_match:
                lb_match.p[0] = loser


class RoundRobin(TournamentEngine):
    """GroupStage (Round-robin): divides players into groups and schedules robin matches."""
    
    def __init__(self, num_players: int, config: Dict[str, Any] = None):
        super().__init__("RoundRobin", num_players, config)
        self._create_matches()
    
    def _create_matches(self):
        n = self.num_players
        if n < 2:
            return
            
        group_size = int(self.config.get("group_size", n)) or n
        if group_size < 2:
            group_size = 2
            
        meet_twice = bool(self.config.get("meet_twice", False))
        
        num_groups = math.ceil(n / group_size)
        all_players = list(range(1, n + 1))
        
        for g in range(num_groups):
            # Players for this group
            start_idx = g * group_size
            end_idx = min(start_idx + group_size, n)
            group_players = all_players[start_idx:end_idx]
            
            if len(group_players) < 2:
                continue
                
            if len(group_players) % 2 == 1:
                group_players.append(0)  # 0 = bye
                
            num_rounds = len(group_players) - 1
            half = len(group_players) // 2
            
            # s = group id (1-indexed)
            group_id = g + 1
            
            for r in range(1, num_rounds + 1):
                match_idx = 0
                for i in range(half):
                    p1 = group_players[i]
                    p2 = group_players[len(group_players) - 1 - i]
                    if p1 == 0 or p2 == 0:
                        continue
                    match_idx += 1
                    
                    self.matches.append(Match(
                        id=MatchId(s=group_id, r=r, m=match_idx),
                        p=[p1, p2]
                    ))
                    
                    if meet_twice:
                        self.matches.append(Match(
                            id=MatchId(s=group_id, r=r + num_rounds, m=match_idx),
                            p=[p2, p1] # Swap home/away
                        ))
                        
                group_players = [group_players[0]] + [group_players[-1]] + group_players[1:-1]


class FFA(TournamentEngine):
    """Free-For-All tournament: multi-round groupings."""
    
    def __init__(self, num_players: int, config: Dict[str, Any] = None):
        super().__init__("FFA", num_players, config)
        self._create_matches()
        
    def _create_matches(self):
        n = self.num_players
        if n < 2:
            return
            
        group_size = int(self.config.get("ffa_group_size", n)) or n
        if group_size < 2:
            group_size = 2
            
        # Only generate R1, advancing is manual
        num_matches = math.ceil(n / group_size)
        for m in range(1, num_matches + 1):
            self.matches.append(Match(
                id=MatchId(s=1, r=1, m=m),
                p=[0] * min(group_size, n - (m-1)*group_size)
            ))
