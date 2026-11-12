"""What a match score must look like before the engine takes it.

The interface only sends sensible scores, but the API is the engine's real door (an admin tool,
an old page, a script): a score that describes a match that cannot happen is refused here, for
admins and players alike, before anything in the bracket moves.
"""
from fastapi import HTTPException

ELIMINATION = ("single_elim", "double_elim")


def merge_scores(existing, sent):
    """A None in the sent score keeps the value already there (each FFA player only sends their own)."""
    existing = existing or []
    out = []
    for i in range(max(len(sent), len(existing))):
        new = sent[i] if i < len(sent) else None
        out.append(new if new is not None else (existing[i] if i < len(existing) else None))
    return out


def check_score(match, sent, config, bracket_type, status):
    """Raise when this score cannot be entered on this match."""
    if status == "CLOSED":
        raise HTTPException(status_code=409, detail="Le tournoi est clôturé : rouvrez-le pour modifier un score.")
    players = match.get("p") or []
    if len(players) < 2 or 0 in players:
        # a match still waiting for a winner from an earlier one, or a bye the server decides
        raise HTTPException(status_code=409, detail="Ce match n'a pas encore tous ses joueurs : il ne peut pas recevoir de score.")
    if len(sent) != len(players):
        raise HTTPException(status_code=400, detail=f"Il faut un score par joueur ou équipe du match ({len(players)}).")
    if any(s is not None and s < 0 for s in sent):
        raise HTTPException(status_code=400, detail="Un score ne peut pas être négatif.")
    if bracket_type == "ffa":
        return

    a, b = merge_scores(match.get("score"), sent)[:2]
    if (a is None) != (b is None):
        raise HTTPException(status_code=400, detail="Il faut le score des deux côtés.")
    if a is None or (a == 0 and b == 0):
        return  # nothing entered, or the score cleared
    if config.get("boolean_mode") and (a > 1 or b > 1):
        raise HTTPException(status_code=400, detail="En mode victoire / défaite, un score vaut 1 (gagné) ou 0 (perdu).")
    if a == b:
        if bracket_type in ELIMINATION:
            raise HTTPException(status_code=400, detail="Un match à élimination doit avoir un vainqueur : pas d'égalité.")
        if not config.get("allow_draws"):
            raise HTTPException(status_code=400, detail="Les égalités ne sont pas autorisées dans ce tournoi.")
