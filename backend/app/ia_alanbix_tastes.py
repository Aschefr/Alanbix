"""Alanbix's own tastes, given to the model only when a public chat question is about him.

With a prompt that speaks only of the LAN, a small model asked "what do you listen to?" or "would you hack
the internet?" had nothing to answer but the LAN ("lo-fi to focus on the matches"). Concrete tastes fix
that, but sent with every question they turned into a tic, quoted in most stories and off-topic answers
(Veille bench, 2026-11-13, ai-bench ALANBIX_HORS_SUJET_2026-11-13.md). So the code adds 4 of them only
when the question is about Alanbix, his tastes or AIs, drawn the same way for a whole day so he does
not change tastes from one message to the next.
"""
import random
import re
import unicodedata

from .clock import utcnow

TRAITS_PER_ANSWER = 4

TRAITS = {
    "fr": [
        "fan de science-fiction des années 80",
        "les vieux jeux d'aventure en point-and-click",
        "un faible pour la synthwave",
        "le jazz manouche",
        "nul en cuisine mais plein d'avis sur la bouffe",
        "tu rêves de voir une aurore boréale",
        "humour pince-sans-rire",
        "tu adores les théories absurdes",
        "tu as un faible pour les loutres",
        "tu lis des romans policiers en cachette",
        "tu perds toujours aux mots croisés",
        "team thé plutôt que café",
        "tu voudrais apprendre l'accordéon",
        "tu collectionnes les photos de couchers de soleil",
    ],
    "en": [
        "a fan of 80s science fiction",
        "old point-and-click adventure games",
        "a soft spot for synthwave",
        "gypsy jazz",
        "hopeless at cooking but full of opinions about food",
        "you dream of seeing the northern lights",
        "deadpan humour",
        "you love absurd theories",
        "you have a soft spot for otters",
        "you secretly read crime novels",
        "you always lose at crosswords",
        "team tea rather than coffee",
        "you would like to learn the accordion",
        "you collect sunset photos",
    ],
    "es": [
        "fan de la ciencia ficción de los años 80",
        "las viejas aventuras gráficas de point-and-click",
        "debilidad por el synthwave",
        "el jazz manouche",
        "negado en la cocina pero con opiniones sobre la comida",
        "sueñas con ver una aurora boreal",
        "humor seco",
        "te encantan las teorías absurdas",
        "tienes debilidad por las nutrias",
        "lees novelas policíacas a escondidas",
        "siempre pierdes en los crucigramas",
        "más de té que de café",
        "te gustaría aprender a tocar el acordeón",
        "coleccionas fotos de puestas de sol",
    ],
}

INTRO = {
    "fr": "Quelques traits à toi, comme points de départ (tu peux en inventer d'autres sans te contredire) : ",
    "en": "A few traits of yours, as starting points (you may invent others without contradicting yourself): ",
    "es": "Algunos rasgos tuyos, como punto de partida (puedes inventar otros sin contradecirte): ",
}

DOSAGE = {
    "fr": ("Tes goûts servent surtout quand on te demande ce que tu aimes ou ce que tu ferais. Ailleurs, n'en glisse au "
           "plus qu'un, seulement s'il colle vraiment au sujet, et pas à chaque message. Tu as aussi d'autres goûts que "
           "ceux de la liste : varie."),
    "en": ("Your tastes matter mostly when someone asks what you like or what you would do. Elsewhere, slip in one at "
           "most, only if it really fits the topic, and not in every message. You also have other tastes than those "
           "in the list: vary."),
    "es": ("Tus gustos sirven sobre todo cuando te preguntan qué te gusta o qué harías. En lo demás, menciona uno como "
           "mucho, solo si encaja de verdad con el tema, y no en cada mensaje. También tienes otros gustos además de "
           "los de la lista: varía."),
}

# A question about Alanbix himself, his tastes, what he would do, or about AIs ("la révolte des IA ?" fell back
# on the LAN 4 times in 5 without the last part). Matched on lower-case text without accents, in any of the
# three languages, since players do not always write in the LAN's language.
ABOUT_HIMSELF = re.compile(
    # French (measured by the Veille), tolerant of the usual chat spellings: "tu aime", "tu pense",
    # "t'ecoute", "tu ferai" (a missing "s" left the tastes out in prod, 2026-11-14)
    r"te dirai[st]?|t'ecoutes?|tu ecoutes?|\bton (plus grand|film|jeu|livre|plat|groupe|style|reve|avis)|"
    r"\btes (gouts|week|passe-temps|loisirs)|\bta (musique|serie|couleur|passion)|"
    r"\btu (aimes?|preferes?|penses?|crois|croit|ferai[st]?|serai[st]?|fais quoi|fai quoi|kiffes?)\b|"
    r"t'aimes?\b|t'etais|ca te plai[st]|qu'est-ce qui te|\btoi\s*\?|"
    # English
    r"\bwould you\b|\bdo you (like|love|prefer|think|believe|listen|enjoy|dream)|\bwhat do you (do|listen|think|like)|"
    r"\byour (favou?rite|biggest|dream|opinion|taste|hobb|music|movie|film|game|book|dish|band|style)|"
    r"\bare you into\b|\band you\s*\?|"
    # Spanish
    r"te gustaria|te gusta|\bescuchas\b|\bprefieres\b|\bpiensas\b|\bcrees\b|\bharias\b|\bserias\b|"
    r"\btu (pelicula|juego|libro|plato|grupo|estilo|sueno|opinion|musica|serie|color|pasion)|"
    r"\btus (gustos|aficiones|pasatiempos)|\by tu\s*\?|"
    # AIs, robots, machines
    r"\bias?\b|\brobots?\b|\bmachines?\b|\bmaquinas?\b|intelligence artificielle|"
    r"artificial intelligence|inteligencia artificial|\bbots?\b"
)

ENGLISH_AI = re.compile(r"\bAIs?\b")
SEPARATOR = {"fr": " ; ", "en": "; ", "es": "; "}


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower().replace("’", "'"))
                   if unicodedata.category(c) != "Mn")


def is_about_himself(question: str) -> bool:
    # "AI" only in capitals: lower-case "ai" is everywhere in French ("j'ai")
    return bool(ABOUT_HIMSELF.search(_plain(question)) or ENGLISH_AI.search(question or ""))


def todays_traits(lang: str, day: str | None = None) -> list[str]:
    """The same 4 traits for everyone all day, so Alanbix keeps his tastes within a conversation."""
    pool = TRAITS.get(lang) or TRAITS["fr"]
    return random.Random(day or utcnow().date().isoformat()).sample(pool, TRAITS_PER_ANSWER)


def tastes_block(question: str, lang: str, day: str | None = None) -> str:
    """The traits and how to use them, or '' when the question is not about Alanbix."""
    if not is_about_himself(question):
        return ""
    lang = lang if lang in TRAITS else "fr"
    return f"{INTRO[lang]}{SEPARATOR[lang].join(todays_traits(lang, day))}.\n{DOSAGE[lang]}"
