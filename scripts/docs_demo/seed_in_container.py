"""Second half of the demo data: what no API can create without a real model
(assistant conversations, help requests, knowledge entries). Runs inside the demo container."""
import os
from datetime import timedelta

from app import database, models
from app.clock import utcnow

FR = os.environ.get("DEMO_LANG", "fr") == "fr"
db = database.SessionLocal()
row = db.query(models.SystemConfig).filter(models.SystemConfig.key == "demo_facts").first()
facts = dict(row.value)
db.delete(row)
opponent, seat, rank, points, other, other_points = (facts["opponent"], facts["opponent_seat"], facts["rank"],
                                                     f'{facts["points"]:g}', facts["other"], f'{facts["other_points"]:g}')


def user(name):
    return db.query(models.User).filter(models.User.username == name).first()


def conversation(name, title, lines, minutes_ago=40, **kwargs):
    conv = models.Conversation(user_id=user(name).id, title=title, model="gemma4:e4b",
                               created_at=utcnow() - timedelta(minutes=minutes_ago), **kwargs)
    db.add(conv)
    db.flush()
    for i, (role, content) in enumerate(lines):
        db.add(models.ChatMessage(conversation_id=conv.id, role=role, content=content,
                                  timestamp=utcnow() - timedelta(minutes=minutes_ago - i)))
    db.flush()
    conv.player_last_read_message_id = max(m.id for m in conv.messages)
    return conv


if FR:
    conversation("PixelHunter", "Mon prochain match", [
        ("user", "C'est quand mon prochain match ?"),
        ("bot", f"Ton prochain match est dans **Iron Arena Showdown**, contre **{opponent}**.\n\n"
                f"{opponent} est à la place **{seat}**. Vous pouvez lancer quand vous êtes prêts, puis l'un de vous saisit le score."),
        ("user", "Et je suis où au classement général ?"),
        ("bot", (f"Tu es **en tête** du classement général avec **{points} points**, devant {other} ({other_points} points)." if rank == 1
                else f"Tu es **{rank}e** du classement général avec **{points} points**. {other} est en tête avec {other_points} points.") + " Il reste plusieurs tournois en cours : rien n'est joué."),
    ], minutes_ago=12)
    conversation("Admin", "Préparer la finale", [
        ("user", "Quels tournois sont encore en cours ?"),
        ("bot", "Quatre tournois sont en cours : **Iron Arena Showdown**, **Neon Drift Grand Prix**, **Goal Rush League** et **Kart Frenzy Cup**. Rocket Duo est encore ouvert aux inscriptions."),
    ], minutes_ago=90)
    stuck = conversation("NightHawk", "Le partage de fichiers ne répond pas", [
        ("user", "Je n'arrive pas à ouvrir le partage où se trouve le patch de Neon Drift."),
        ("bot", "Le patch est aussi disponible en téléchargement direct, en bas de la page **Infos**. Essaie aussi de rouvrir le dossier réseau indiqué sur cette page.\n\nSi le partage reste inaccessible, je peux prévenir un organisateur."),
        ("user", "Toujours rien, tu peux prévenir quelqu'un ?"),
        ("bot", "J'ai prévenu les organisateurs : quelqu'un va passer te voir à la place **T1_S8**."),
        ("bot", "Bonjour NightHawk, c'est l'organisation : le partage vient de redémarrer, tu peux réessayer."),
    ], minutes_ago=25, admin_override=True)
    db.add(models.AdminCallRequest(user_id=user("NightHawk").id, conversation_id=stuck.id, source="ia", status="pending",
                                   reason="Le partage réseau du patch ne répond pas sur ce poste.",
                                   question="Peut-on vérifier le partage de fichiers de la LAN ?"))
    db.add(models.AdminCallRequest(user_id=user("IcePhoenix").id, source="manual", status="pending",
                                   reason="Besoin d'un câble réseau plus long.",
                                   question="Y a-t-il un câble de 5 m disponible ?"))
    entries = [
        ("Le petit-déjeuner est servi de 8 h à 10 h, au bar. Les boissons chaudes sont gratuites toute la journée.", "Repas"),
        ("Un câble réseau de rechange et une multiprise s'empruntent à l'accueil, contre une pièce d'identité.", "Matériel"),
        ("Le parking gratuit se trouve derrière la salle. Merci de ne pas bloquer le portail de livraison.", "Accès"),
    ]
else:
    conversation("PixelHunter", "My next match", [
        ("user", "When is my next match?"),
        ("bot", f"Your next match is in **Iron Arena Showdown**, against **{opponent}**.\n\n"
                f"{opponent} is at seat **{seat}**. Start whenever you are both ready, then either of you enters the score."),
        ("user", "And where am I on the overall leaderboard?"),
        ("bot", (f"You are **in the lead** overall with **{points} points**, ahead of {other} ({other_points} points)." if rank == 1
                else f"You are **number {rank}** overall with **{points} points**. {other} leads with {other_points} points.") + " Several tournaments are still running, so nothing is settled."),
    ], minutes_ago=12)
    conversation("Admin", "Getting the final ready", [
        ("user", "Which tournaments are still running?"),
        ("bot", "Four tournaments are running: **Iron Arena Showdown**, **Neon Drift Grand Prix**, **Goal Rush League** and **Kart Frenzy Cup**. Rocket Duo is still open for sign-ups."),
    ], minutes_ago=90)
    stuck = conversation("NightHawk", "The file share does not respond", [
        ("user", "I can't open the share with the Neon Drift patch."),
        ("bot", "The patch can also be downloaded directly, at the bottom of the **Info** page. Also try opening the network folder listed on that page again.\n\nIf the share stays out of reach, I can alert an organiser."),
        ("user", "Still nothing, can you tell someone?"),
        ("bot", "I have alerted the organisers: someone will come to you at seat **T1_S8**."),
        ("bot", "Hi NightHawk, organisers here: the share has just restarted, please try again."),
    ], minutes_ago=25, admin_override=True)
    db.add(models.AdminCallRequest(user_id=user("NightHawk").id, conversation_id=stuck.id, source="ia", status="pending",
                                   reason="The network share with the patch does not respond from this seat.",
                                   question="Can someone check the LAN file share?"))
    db.add(models.AdminCallRequest(user_id=user("IcePhoenix").id, source="manual", status="pending",
                                   reason="Needs a longer network cable.",
                                   question="Is a 5 m cable available?"))
    entries = [
        ("Breakfast is served from 8 to 10 am at the bar. Hot drinks are free all day.", "Meals"),
        ("A spare network cable and a power strip can be borrowed at the front desk, against an ID.", "Equipment"),
        ("Free parking is behind the venue. Please do not block the delivery gate.", "Access"),
    ]

for content, category in entries:
    db.add(models.KnowledgeBase(content=content, metadata_json={"category": category}))
db.commit()
print("container seed done")
