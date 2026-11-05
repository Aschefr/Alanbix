"""Messages written by the AI for the players when a tournament closes."""
import asyncio
import json
from .. import models
from ..websockets import manager
from .awards import get_i18n_dict


def _build_player_narratives(bracket, bracket_type, results, config, db, participant_uids, use_teams):
    """Extract per-player narrative facts from bracket data for richer AI prompts."""
    narratives = {}  # entity_id -> list of facts
    lower_is_better = config.get("lower_score_is_better", False)

    if not bracket:
        return narratives

    # Build name map for all entities
    name_map = {}
    for r in results:
        name_map[r.get("entity_id")] = r.get("name", "?")
    for uid in participant_uids:
        if uid not in name_map:
            user = db.query(models.User).filter(models.User.id == uid).first()
            if user:
                name_map[uid] = user.username

    # Analyze each entity's matches
    all_entities = set()
    for m in bracket:
        for pid in m.get("p", []):
            if pid and pid != 0:
                all_entities.add(pid)

    max_wb_round = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 1), default=0)
    max_lb_round = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 2), default=0)

    for eid in all_entities:
        facts = []
        wins = 0
        losses = 0
        streak = 0
        max_streak = 0
        biggest_win_delta = 0
        biggest_win_label = ""
        closest_match_delta = 999
        closest_match_label = ""
        was_in_lb = False
        reached_gf = False
        elim_round = None
        elim_section = None

        # Gather matches involving this entity, sorted by section then round
        entity_matches = sorted(
            [m for m in bracket if eid in m.get("p", [])],
            key=lambda m: (m["id"]["s"], m["id"]["r"])
        )

        for m in entity_matches:
            p = m.get("p", [])
            s = m.get("score", [])
            mid = m["id"]
            if len(s) < 2 or (s[0] == 0 and s[1] == 0):
                continue  # Unscored
            if 0 in p:
                continue  # BYE

            idx = p.index(eid) if eid in p else -1
            if idx < 0:
                continue
            opp_idx = 1 - idx

            my_score = s[idx] if idx < len(s) else 0
            opp_score = s[opp_idx] if opp_idx < len(s) else 0

            if my_score == opp_score:
                continue  # Tie, no resolution

            if lower_is_better:
                won = my_score < opp_score
            else:
                won = my_score > opp_score

            delta = abs(my_score - opp_score)
            round_label = f"Manche {mid['r']}"
            if bracket_type == "double_elim":
                if mid["s"] == 2:
                    round_label = f"Manche {mid['r']} du Losers Bracket"
                elif mid["r"] == max_wb_round:
                    round_label = "Finale"
                else:
                    round_label = f"Manche {mid['r']} du Winners Bracket"

            if won:
                wins += 1
                streak += 1
                max_streak = max(max_streak, streak)
                if delta > biggest_win_delta:
                    biggest_win_delta = delta
                    biggest_win_label = f"{my_score}-{opp_score} ({round_label})"
            else:
                losses += 1
                streak = 0
                elim_round = mid["r"]
                elim_section = mid["s"]

            if delta < closest_match_delta and delta > 0:
                closest_match_delta = delta
                closest_match_label = f"{my_score}-{opp_score} ({round_label})"

            # Track LB presence
            if mid["s"] == 2:
                was_in_lb = True
            # Track Grand Final presence
            if mid["s"] == 1 and mid["r"] == max_wb_round:
                reached_gf = True

        # Build narrative
        if wins + losses > 0:
            facts.append(f"Bilan : {wins} victoire{'s' if wins > 1 else ''}, {losses} défaite{'s' if losses > 1 else ''}")

        if max_streak >= 3:
            facts.append(f"Streak : {max_streak} victoires consécutives")

        if biggest_win_delta >= 2 and biggest_win_label:
            facts.append(f"Score le plus large : {biggest_win_label}")

        if closest_match_delta <= 2 and closest_match_label and (wins + losses) > 1:
            facts.append(f"Match le plus serré : {closest_match_label}")

        # Comeback detection (double_elim specific)
        if bracket_type == "double_elim" and was_in_lb and reached_gf:
            facts.append("🔥 Reverse sweep depuis le Losers Bracket !")

        # Early elimination
        if losses > 0 and elim_round and not reached_gf:
            total_rounds = max_wb_round
            if bracket_type in ("single_elim", "double_elim") and elim_round <= total_rounds // 2:
                facts.append(f"Éliminé au Round {elim_round} sur {total_rounds}")

        # Team members
        if use_teams and eid < 0:
            team_id = abs(eid)
            members = db.query(models.TournamentTeamMember).filter(
                models.TournamentTeamMember.team_id == team_id
            ).all()
            member_names = []
            for m in members:
                user = db.query(models.User).filter(models.User.id == m.user_id).first()
                if user:
                    member_names.append(user.username)
            if member_names:
                facts.append(f"Membres : {', '.join(member_names)}")

        if facts:
            narratives[eid] = facts

    return narratives


def _build_closing_prompt(tournament_name, game_name, results, participant_uids, use_teams, bracket, config, db):
    """Build the full prompt for Ollama closing notifications. Reusable by both generation and preview."""
    bracket_type = config.get("bracket_type", "single_elim")
    bracket_labels = {
        "single_elim": "Élimination Directe",
        "double_elim": "Double Élimination",
        "round_robin": "Championnat (Round Robin)",
        "ffa": "Free For All"
    }

    # Read active closing prompt
    from .ia import get_active_closing_prompt
    intro = get_active_closing_prompt(db)

    # Build standings summary
    standings_text = ""
    player_names = []
    for r in results:
        rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r.get("rank"), f"#{r.get('rank', '?')}")
        standings_text += f"{rank_emoji} {r['name']} — {r.get('total', 0)} pts (Placement: {r.get('placement_pts', 0)}, Bonus: {r.get('score_pts', 0)}, Participation: {r.get('participation_pts', 0)})\n"
        player_names.append(r['name'])

    # Also get usernames for solo mode participants not in standings
    if not use_teams:
        for uid in participant_uids:
            user = db.query(models.User).filter(models.User.id == uid).first()
            if user and user.username not in player_names:
                player_names.append(user.username)
                standings_text += f"  {user.username} — participant\n"

    # Build narratives
    narratives = _build_player_narratives(bracket, bracket_type, results, config, db, participant_uids, use_teams)
    narratives_text = ""
    for r in results:
        eid = r.get("entity_id")
        name = r.get("name", "?")
        facts = narratives.get(eid, [])
        if facts:
            narratives_text += f"{name} : {'. '.join(facts)}.\n"
    # Add narratives for participants not in results
    if not use_teams:
        for uid in participant_uids:
            if uid not in [r.get("entity_id") for r in results]:
                facts = narratives.get(uid, [])
                user = db.query(models.User).filter(models.User.id == uid).first()
                name = user.username if user else f"#{uid}"
                if facts:
                    narratives_text += f"{name} : {'. '.join(facts)}.\n"

    prompt = f"{intro}\n"
    prompt += f'Le tournoi "{tournament_name}" ({game_name or "jeu inconnu"}) vient de se terminer !\n'
    prompt += f"Format : {bracket_labels.get(bracket_type, bracket_type)} — {len(participant_uids)} joueurs\n\n"
    prompt += f"=== Résultats ===\n{standings_text}\n"
    if narratives_text:
        prompt += f"=== Faits Marquants par Joueur ===\n{narratives_text}\n"
    prompt += (
        'Génère un message COURT (1-2 phrases max), personnalisé et humoristique pour CHAQUE joueur/équipe.\n'
        'Utilise les faits marquants ci-dessus pour personnaliser chaque message.\n'
        'Réponds UNIQUEMENT en JSON valide, sans markdown, sans backticks :\n'
        '{"messages": [{"player": "nom", "message": "ton message"}, ...]}'
    )
    return prompt


async def _generate_tournament_notifications(tournament_id, tournament_name, game_name, results, participant_uids, use_teams, bracket=None, config=None):
    """Fire-and-forget: Ask Ollama to generate personalized messages for participants (via AI queue)."""
    bracket = bracket or []
    config = config or {}
    try:
        from .ia import pick_instance, get_effective_config
        from ..database import SessionLocal
        from ..ia_queue import queue_manager, QueueEntry
        import time

        db = SessionLocal()
        try:
            ia_cfg = get_effective_config(db)
            instance = await pick_instance(db)
            if not instance:
                print("[Tournaments] No AI instance configured, skipping closing notifications")
                return
            ollama_host = instance["url"]
            model = instance.get("model") or ia_cfg.get('model', '')

            prompt = _build_closing_prompt(
                tournament_name, game_name, results, participant_uids,
                use_teams, bracket, config, db
            )

            # Enqueue through AI queue (priority 20 = background)
            entry = QueueEntry(
                priority=20,
                created_at=time.time(),
                user_id=0,  # System task, no user limit
                username=f"[Tournoi] {tournament_name}",
                conversation_id=0,
                task_type="notification",
                payload={
                    "ollama_host": ollama_host,
                    "model": model,
                    "prompt": prompt,
                    "context_window": ia_cfg.get("context_window", 4096),
                }
            )
            entry, _ = await queue_manager.enqueue(entry)

            # Wait for the worker to finish (with generous timeout for background task)
            await asyncio.wait_for(entry.done_event.wait(), timeout=180.0)

            # Read result
            result_data = await entry.result_stream.get()
            if result_data.get("error"):
                raise Exception(result_data.get("result", "Erreur de génération IA"))

            raw = result_data.get("result", "")
            # Clean up potential markdown wrapping
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)
            ai_messages = data.get("messages", [])

            # Map player names to user IDs
            name_to_uid = {}
            for uid in participant_uids:
                user = db.query(models.User).filter(models.User.id == uid).first()
                if user:
                    name_to_uid[user.username.lower()] = uid

            # Also map team names to member UIDs
            if use_teams:
                for r in results:
                    if r.get("entity_id") and isinstance(r["entity_id"], int) and r["entity_id"] < 0:
                        team_id = abs(r["entity_id"])
                        members = db.query(models.TournamentTeamMember).filter(
                            models.TournamentTeamMember.team_id == team_id
                        ).all()
                        name_to_uid[r["name"].lower()] = [m.user_id for m in members]

            # Create notifications
            for ai_msg in ai_messages:
                player_name = ai_msg.get("player", "").lower()
                message = ai_msg.get("message", "")
                if not message:
                    continue

                target_uids = name_to_uid.get(player_name, [])
                if isinstance(target_uids, int):
                    target_uids = [target_uids]

                for uid in target_uids:
                    notif = models.Notification(
                        user_id=uid,
                        type="tournament_closed",
                        title=f"🏆 {tournament_name}",
                        content=message,
                        metadata_json={"tournament_id": tournament_id}
                    )
                    db.add(notif)

            db.commit()
            # Broadcast to all clients that new notifications are available
            await manager.broadcast({"type": "notification_new"})

        finally:
            db.close()
    except Exception as e:
        # Notify all admins about the failure
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)[:300]}"
        try:
            from ..database import SessionLocal
            err_db = SessionLocal()
            try:
                admins = err_db.query(models.User).filter(models.User.is_admin == True).all()
                # Stored in the language of the LAN; the app shows it in each admin's language
                config_lang = err_db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
                i18n = get_i18n_dict(config_lang.value if config_lang else "fr")
                failed_title = i18n.get("notif_ai_failed_title", "Échec IA — {tournament}").replace("{tournament}", tournament_name)
                failed_body = i18n.get("notif_ai_failed_body", "La génération de messages personnalisés a échoué.")
                for admin in admins:
                    notif = models.Notification(
                        user_id=admin.id,
                        type="system",
                        title=f"⚠️ {failed_title}",
                        content=f"{failed_body}\n{error_detail}",
                        metadata_json={"tournament_id": tournament_id, "tournament_name": tournament_name, "error_detail": error_detail, "error": True}
                    )
                    err_db.add(notif)
                err_db.commit()
                await manager.broadcast({"type": "notification_new"})
            finally:
                err_db.close()
        except Exception:
            pass  # Last resort
