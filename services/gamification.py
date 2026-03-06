"""Gamification service — XP, streaks, badges, levels, themes."""
import logging
from datetime import date, timedelta
from math import floor, sqrt
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 5 THEMES
# ---------------------------------------------------------------------------

THEMES = {
    "neutral": {
        "name": "Neutral",
        "display_name": "Neitral'nyj",
        "xp_name": "XP", "xp_emoji": "\u2728",
        "streak_name": "Seriya", "streak_emoji": "\U0001f525",
        "levels": [
            "Uroven' 1", "Uroven' 2", "Uroven' 3", "Uroven' 4", "Uroven' 5",
            "Uroven' 6", "Uroven' 7", "Uroven' 8", "Uroven' 9", "Uroven' 10",
        ],
        "correct_msg": "\u2705 Pravil'no!",
        "wrong_msg": "\u274c Nepravil'no.",
        "perfect_msg": "\U0001f3c6 Otlichnyj rezul'tat!",
        "good_msg": "\U0001f44d Horoshij rezul'tat!",
        "ok_msg": "\U0001f4d6 Neplokho, no est' nad chem porabotat'.",
        "weak_msg": "\U0001f4aa Nuzhno eshchyo potrenirovatsya!",
        "xp_earn": "+{xp} XP",
        "streak_msg": "\U0001f525 Seriya: {days} dn. podryad!",
        "level_msg": "\U0001f4c8 Uroven' {level} ({xp}/{next_xp} do sleduyushchego)",
        "badge_msg": "\U0001f3c5 Novyj znachok: \"{name}\"!",
    },
    "minecraft": {
        "name": "Minecraft",
        "display_name": "\u26cf Minecraft",
        "xp_name": "Opyt", "xp_emoji": "\U0001f48e",
        "streak_name": "Dni dobychi", "streak_emoji": "\u26cf\ufe0f",
        "levels": [
            "Derevyannyj", "Kamennyj", "Zheleznyj", "Zolotoj",
            "Almaznyj", "Nezeritovyj",
        ],
        "correct_msg": "\u2705 Blok dobyt!",
        "wrong_msg": "\U0001f480 Kriper vzorval otvet!",
        "perfect_msg": "\U0001f3c6 Drakon poverzhen!",
        "good_msg": "\u26cf\ufe0f Neplokhaya dobycha!",
        "ok_msg": "\U0001f9f1 Mozhno kopnut' glubzhe!",
        "weak_msg": "\U0001f6e1\ufe0f Nuzhen novyj kirku!",
        "xp_earn": "\U0001f48e +{xp} Opyt",
        "streak_msg": "\u26cf\ufe0f Dni dobychi: {days} podryad!",
        "level_msg": "\U0001f4c8 {level} uroven' ({xp}/{next_xp} do sleduyushchego)",
        "badge_msg": "\U0001f3c5 Dostizhenie razbloksirovano: \"{name}\"!",
    },
    "ninjago": {
        "name": "Lego Ninjago",
        "display_name": "\U0001f977 Lego Ninjago",
        "xp_name": "Energiya", "xp_emoji": "\u26a1",
        "streak_name": "Dni trenirovki", "streak_emoji": "\U0001f977",
        "levels": [
            "Uchenik", "Nindzya", "Master", "Sensej", "Grandmaster",
        ],
        "correct_msg": "\u2705 Sila stikhii rastyot!",
        "wrong_msg": "\U0001f4a8 Protivnik otrazil udar!",
        "perfect_msg": "\U0001f3c6 Ty — istinnyj nindzya!",
        "good_msg": "\u26a1 Khoroshaya trenirovka!",
        "ok_msg": "\U0001f94b Prodolzhaj trenirovku!",
        "weak_msg": "\U0001f977 Sensej zhyot v dodzhyo!",
        "xp_earn": "\u26a1 +{xp} Energiya",
        "streak_msg": "\U0001f977 Dni trenirovki: {days} podryad!",
        "level_msg": "\U0001f4c8 {level} ({xp}/{next_xp} do sleduyushchego)",
        "badge_msg": "\U0001f3c5 Novyj poyas: \"{name}\"!",
    },
    "space": {
        "name": "Kosmos",
        "display_name": "\U0001f680 Kosmos",
        "xp_name": "Toplivo", "xp_emoji": "\U0001f680",
        "streak_name": "Dni polyota", "streak_emoji": "\U0001f31f",
        "levels": [
            "Kadet", "Pilot", "Kapitan", "Komandor", "Admiral",
        ],
        "correct_msg": "\u2705 Tochnoye popadaniye!",
        "wrong_msg": "\U0001f4ab Asteroid otklonilsya!",
        "perfect_msg": "\U0001f3c6 Missiya vypolnena blistatel'no!",
        "good_msg": "\U0001f680 Korabl' nabirayot skorost'!",
        "ok_msg": "\U0001f30d Nuzhna korrektsiya kursa!",
        "weak_msg": "\U0001f6f8 Zaprosi podkrepleniye!",
        "xp_earn": "\U0001f680 +{xp} Toplivo",
        "streak_msg": "\U0001f31f Dni polyota: {days} podryad!",
        "level_msg": "\U0001f4c8 {level} ({xp}/{next_xp} do sleduyushchego)",
        "badge_msg": "\U0001f3c5 Novaya planeta otkryta: \"{name}\"!",
    },
    "superhero": {
        "name": "Supergeroj",
        "display_name": "\U0001f9b8 Supergeroj",
        "xp_name": "Sila", "xp_emoji": "\U0001f4a5",
        "streak_name": "Dni podvigov", "streak_emoji": "\U0001f9b8",
        "levels": [
            "Novichok", "Geroj", "Supergeroj", "Legenda", "Titan",
        ],
        "correct_msg": "\u2705 Supersila aktivirovana!",
        "wrong_msg": "\U0001f4a2 Zlodej ushyol ot udara!",
        "perfect_msg": "\U0001f3c6 Gorod spasen!",
        "good_msg": "\U0001f4a5 Khorosha rabota, geroj!",
        "ok_msg": "\U0001f9e0 Nuzhno uluchshit' navyki!",
        "weak_msg": "\U0001f9b8 Trenirovka v shtab-kvartire!",
        "xp_earn": "\U0001f4a5 +{xp} Sila",
        "streak_msg": "\U0001f9b8 Dni podvigov: {days} podryad!",
        "level_msg": "\U0001f4c8 {level} ({xp}/{next_xp} do sleduyushchego)",
        "badge_msg": "\U0001f3c5 Novaya sposobnost': \"{name}\"!",
    },
}

# Override with proper Russian text
THEMES["neutral"]["display_name"] = "\u2b50 \u041d\u0435\u0439\u0442\u0440\u0430\u043b\u044c\u043d\u044b\u0439"
THEMES["neutral"]["levels"] = [f"\u0423\u0440\u043e\u0432\u0435\u043d\u044c {i}" for i in range(1, 11)]
THEMES["neutral"]["correct_msg"] = "\u2705 \u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e!"
THEMES["neutral"]["wrong_msg"] = "\u274c \u041d\u0435\u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e."
THEMES["neutral"]["perfect_msg"] = "\U0001f3c6 \u041e\u0442\u043b\u0438\u0447\u043d\u044b\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442!"
THEMES["neutral"]["good_msg"] = "\U0001f44d \u0425\u043e\u0440\u043e\u0448\u0438\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442!"
THEMES["neutral"]["ok_msg"] = "\U0001f4d6 \u041d\u0435\u043f\u043b\u043e\u0445\u043e, \u043d\u043e \u0435\u0441\u0442\u044c \u043d\u0430\u0434 \u0447\u0435\u043c \u043f\u043e\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c."
THEMES["neutral"]["weak_msg"] = "\U0001f4aa \u041d\u0443\u0436\u043d\u043e \u0435\u0449\u0451 \u043f\u043e\u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f!"
THEMES["neutral"]["xp_earn"] = "\u2728 +{xp} XP"
THEMES["neutral"]["streak_msg"] = "\U0001f525 \u0421\u0435\u0440\u0438\u044f: {days} \u0434\u043d. \u043f\u043e\u0434\u0440\u044f\u0434!"
THEMES["neutral"]["level_msg"] = "\U0001f4c8 \u0423\u0440\u043e\u0432\u0435\u043d\u044c {level} ({xp}/{next_xp} \u0434\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0433\u043e)"
THEMES["neutral"]["badge_msg"] = "\U0001f3c5 \u041d\u043e\u0432\u044b\u0439 \u0437\u043d\u0430\u0447\u043e\u043a: \"{name}\"!"

THEMES["minecraft"]["display_name"] = "\u26cf\ufe0f Minecraft"
THEMES["minecraft"]["levels"] = ["\u0414\u0435\u0440\u0435\u0432\u044f\u043d\u043d\u044b\u0439", "\u041a\u0430\u043c\u0435\u043d\u043d\u044b\u0439", "\u0416\u0435\u043b\u0435\u0437\u043d\u044b\u0439", "\u0417\u043e\u043b\u043e\u0442\u043e\u0439", "\u0410\u043b\u043c\u0430\u0437\u043d\u044b\u0439", "\u041d\u0435\u0437\u0435\u0440\u0438\u0442\u043e\u0432\u044b\u0439"]
THEMES["minecraft"]["correct_msg"] = "\u2705 \u0411\u043b\u043e\u043a \u0434\u043e\u0431\u044b\u0442!"
THEMES["minecraft"]["wrong_msg"] = "\U0001f480 \u041a\u0440\u0438\u043f\u0435\u0440 \u0432\u0437\u043e\u0440\u0432\u0430\u043b \u043e\u0442\u0432\u0435\u0442!"
THEMES["minecraft"]["perfect_msg"] = "\U0001f3c6 \u0414\u0440\u0430\u043a\u043e\u043d \u043f\u043e\u0432\u0435\u0440\u0436\u0435\u043d!"
THEMES["minecraft"]["good_msg"] = "\u26cf\ufe0f \u041d\u0435\u043f\u043b\u043e\u0445\u0430\u044f \u0434\u043e\u0431\u044b\u0447\u0430!"
THEMES["minecraft"]["ok_msg"] = "\U0001f9f1 \u041c\u043e\u0436\u043d\u043e \u043a\u043e\u043f\u043d\u0443\u0442\u044c \u0433\u043b\u0443\u0431\u0436\u0435!"
THEMES["minecraft"]["weak_msg"] = "\U0001f6e1\ufe0f \u041d\u0443\u0436\u0435\u043d \u043d\u043e\u0432\u044b\u0439 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442!"
THEMES["minecraft"]["xp_earn"] = "\U0001f48e +{xp} \u041e\u043f\u044b\u0442"
THEMES["minecraft"]["streak_msg"] = "\u26cf\ufe0f \u0414\u043d\u0438 \u0434\u043e\u0431\u044b\u0447\u0438: {days} \u043f\u043e\u0434\u0440\u044f\u0434!"
THEMES["minecraft"]["level_msg"] = "\U0001f4c8 {level} \u0443\u0440\u043e\u0432\u0435\u043d\u044c ({xp}/{next_xp} \u0434\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0433\u043e)"
THEMES["minecraft"]["badge_msg"] = "\U0001f3c5 \u0414\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u0435: \"{name}\"!"

THEMES["ninjago"]["display_name"] = "\U0001f977 Lego Ninjago"
THEMES["ninjago"]["levels"] = ["\u0423\u0447\u0435\u043d\u0438\u043a", "\u041d\u0438\u043d\u0434\u0437\u044f", "\u041c\u0430\u0441\u0442\u0435\u0440", "\u0421\u044d\u043d\u0441\u044d\u0439", "\u0413\u0440\u0430\u043d\u0434\u043c\u0430\u0441\u0442\u0435\u0440"]
THEMES["ninjago"]["correct_msg"] = "\u2705 \u0421\u0438\u043b\u0430 \u0441\u0442\u0438\u0445\u0438\u0438 \u0440\u0430\u0441\u0442\u0451\u0442!"
THEMES["ninjago"]["wrong_msg"] = "\U0001f4a8 \u041f\u0440\u043e\u0442\u0438\u0432\u043d\u0438\u043a \u043e\u0442\u0440\u0430\u0437\u0438\u043b \u0443\u0434\u0430\u0440!"
THEMES["ninjago"]["perfect_msg"] = "\U0001f3c6 \u0422\u044b \u2014 \u0438\u0441\u0442\u0438\u043d\u043d\u044b\u0439 \u043d\u0438\u043d\u0434\u0437\u044f!"
THEMES["ninjago"]["good_msg"] = "\u26a1 \u0425\u043e\u0440\u043e\u0448\u0430\u044f \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430!"
THEMES["ninjago"]["ok_msg"] = "\U0001f94b \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0439 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0443!"
THEMES["ninjago"]["weak_msg"] = "\U0001f977 \u0421\u044d\u043d\u0441\u044d\u0439 \u0436\u0434\u0451\u0442 \u0432 \u0434\u043e\u0434\u0436\u043e!"
THEMES["ninjago"]["xp_earn"] = "\u26a1 +{xp} \u042d\u043d\u0435\u0440\u0433\u0438\u044f"
THEMES["ninjago"]["streak_msg"] = "\U0001f977 \u0414\u043d\u0438 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0438: {days} \u043f\u043e\u0434\u0440\u044f\u0434!"
THEMES["ninjago"]["level_msg"] = "\U0001f4c8 {level} ({xp}/{next_xp} \u0434\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0433\u043e)"
THEMES["ninjago"]["badge_msg"] = "\U0001f3c5 \u041d\u043e\u0432\u044b\u0439 \u043f\u043e\u044f\u0441: \"{name}\"!"

THEMES["space"]["display_name"] = "\U0001f680 \u041a\u043e\u0441\u043c\u043e\u0441"
THEMES["space"]["levels"] = ["\u041a\u0430\u0434\u0435\u0442", "\u041f\u0438\u043b\u043e\u0442", "\u041a\u0430\u043f\u0438\u0442\u0430\u043d", "\u041a\u043e\u043c\u0430\u043d\u0434\u043e\u0440", "\u0410\u0434\u043c\u0438\u0440\u0430\u043b"]
THEMES["space"]["correct_msg"] = "\u2705 \u0422\u043e\u0447\u043d\u043e\u0435 \u043f\u043e\u043f\u0430\u0434\u0430\u043d\u0438\u0435!"
THEMES["space"]["wrong_msg"] = "\U0001f4ab \u0410\u0441\u0442\u0435\u0440\u043e\u0438\u0434 \u043e\u0442\u043a\u043b\u043e\u043d\u0438\u043b\u0441\u044f!"
THEMES["space"]["perfect_msg"] = "\U0001f3c6 \u041c\u0438\u0441\u0441\u0438\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430 \u0431\u043b\u0438\u0441\u0442\u0430\u0442\u0435\u043b\u044c\u043d\u043e!"
THEMES["space"]["good_msg"] = "\U0001f680 \u041a\u043e\u0440\u0430\u0431\u043b\u044c \u043d\u0430\u0431\u0438\u0440\u0430\u0435\u0442 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u044c!"
THEMES["space"]["ok_msg"] = "\U0001f30d \u041d\u0443\u0436\u043d\u0430 \u043a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f \u043a\u0443\u0440\u0441\u0430!"
THEMES["space"]["weak_msg"] = "\U0001f6f8 \u0417\u0430\u043f\u0440\u043e\u0441\u0438 \u043f\u043e\u0434\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u0438\u0435!"
THEMES["space"]["xp_earn"] = "\U0001f680 +{xp} \u0422\u043e\u043f\u043b\u0438\u0432\u043e"
THEMES["space"]["streak_msg"] = "\U0001f31f \u0414\u043d\u0438 \u043f\u043e\u043b\u0451\u0442\u0430: {days} \u043f\u043e\u0434\u0440\u044f\u0434!"
THEMES["space"]["level_msg"] = "\U0001f4c8 {level} ({xp}/{next_xp} \u0434\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0433\u043e)"
THEMES["space"]["badge_msg"] = "\U0001f3c5 \u041d\u043e\u0432\u0430\u044f \u043f\u043b\u0430\u043d\u0435\u0442\u0430: \"{name}\"!"

THEMES["superhero"]["display_name"] = "\U0001f9b8 \u0421\u0443\u043f\u0435\u0440\u0433\u0435\u0440\u043e\u0439"
THEMES["superhero"]["levels"] = ["\u041d\u043e\u0432\u0438\u0447\u043e\u043a", "\u0413\u0435\u0440\u043e\u0439", "\u0421\u0443\u043f\u0435\u0440\u0433\u0435\u0440\u043e\u0439", "\u041b\u0435\u0433\u0435\u043d\u0434\u0430", "\u0422\u0438\u0442\u0430\u043d"]
THEMES["superhero"]["correct_msg"] = "\u2705 \u0421\u0443\u043f\u0435\u0440\u0441\u0438\u043b\u0430 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u0430!"
THEMES["superhero"]["wrong_msg"] = "\U0001f4a2 \u0417\u043b\u043e\u0434\u0435\u0439 \u0443\u0448\u0451\u043b \u043e\u0442 \u0443\u0434\u0430\u0440\u0430!"
THEMES["superhero"]["perfect_msg"] = "\U0001f3c6 \u0413\u043e\u0440\u043e\u0434 \u0441\u043f\u0430\u0441\u0451\u043d!"
THEMES["superhero"]["good_msg"] = "\U0001f4a5 \u0425\u043e\u0440\u043e\u0448\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430, \u0433\u0435\u0440\u043e\u0439!"
THEMES["superhero"]["ok_msg"] = "\U0001f9e0 \u041d\u0443\u0436\u043d\u043e \u0443\u043b\u0443\u0447\u0448\u0438\u0442\u044c \u043d\u0430\u0432\u044b\u043a\u0438!"
THEMES["superhero"]["weak_msg"] = "\U0001f9b8 \u0422\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430 \u0432 \u0448\u0442\u0430\u0431-\u043a\u0432\u0430\u0440\u0442\u0438\u0440\u0435!"
THEMES["superhero"]["xp_earn"] = "\U0001f4a5 +{xp} \u0421\u0438\u043b\u0430"
THEMES["superhero"]["streak_msg"] = "\U0001f9b8 \u0414\u043d\u0438 \u043f\u043e\u0434\u0432\u0438\u0433\u043e\u0432: {days} \u043f\u043e\u0434\u0440\u044f\u0434!"
THEMES["superhero"]["level_msg"] = "\U0001f4c8 {level} ({xp}/{next_xp} \u0434\u043e \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0433\u043e)"
THEMES["superhero"]["badge_msg"] = "\U0001f3c5 \u041d\u043e\u0432\u0430\u044f \u0441\u043f\u043e\u0441\u043e\u0431\u043d\u043e\u0441\u0442\u044c: \"{name}\"!"

# ---------------------------------------------------------------------------
# BADGES
# ---------------------------------------------------------------------------

BADGES = {
    "first_quiz":    ("\U0001f3af", "\u041f\u0435\u0440\u0432\u044b\u0439 \u0442\u0435\u0441\u0442"),
    "perfect_score": ("\U0001f48e", "\u041f\u0435\u0440\u0444\u0435\u043a\u0446\u0438\u043e\u043d\u0438\u0441\u0442"),
    "streak_3":      ("\U0001f525", "3 \u0434\u043d\u044f \u043f\u043e\u0434\u0440\u044f\u0434"),
    "streak_7":      ("\u2b50", "7 \u0434\u043d\u0435\u0439 \u043f\u043e\u0434\u0440\u044f\u0434"),
    "streak_30":     ("\U0001f3c6", "30 \u0434\u043d\u0435\u0439 \u043f\u043e\u0434\u0440\u044f\u0434"),
    "tests_10":      ("\U0001f4da", "\u0414\u0435\u0441\u044f\u0442\u043e\u0447\u043a\u0430"),
    "tests_50":      ("\U0001f9e0", "\u0417\u043d\u0430\u0442\u043e\u043a"),
    "level_5":       ("\U0001f31f", "5 \u0443\u0440\u043e\u0432\u0435\u043d\u044c"),
    "speed_demon":   ("\u26a1", "\u041c\u043e\u043b\u043d\u0438\u044f"),
    "polyglot":      ("\U0001f30d", "\u041f\u043e\u043b\u0438\u0433\u043b\u043e\u0442"),
    "explorer":      ("\U0001f5fa\ufe0f", "\u0418\u0441\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c"),
}


# ---------------------------------------------------------------------------
# LEVEL CALCULATIONS
# ---------------------------------------------------------------------------

def xp_for_level(level: int) -> int:
    """XP required to reach a given level. level=1 -> 0, level=2 -> 100, etc."""
    if level <= 1:
        return 0
    return (level - 1) ** 2 * 100


def level_from_xp(xp: int) -> int:
    """Calculate level from total XP."""
    return 1 + floor(sqrt(xp / 100)) if xp > 0 else 1


def get_level_name(theme_key: str, level: int) -> str:
    """Get the display name for a level in a given theme."""
    theme = THEMES.get(theme_key, THEMES["neutral"])
    levels = theme["levels"]
    idx = min(level - 1, len(levels) - 1)
    return levels[max(0, idx)]


def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Render a text progress bar."""
    if total <= 0:
        return "\u2591" * length + " 0%"
    filled = round(current / total * length)
    filled = min(filled, length)
    bar = "\u2593" * filled + "\u2591" * (length - filled)
    pct = round(current / total * 100)
    return f"{bar} {pct}%"


# ---------------------------------------------------------------------------
# XP CALCULATION
# ---------------------------------------------------------------------------

def calculate_xp(correct: int, total: int, streak_days: int, answer_times: Optional[list[float]] = None) -> int:
    """Calculate XP earned from a quiz session.

    Args:
        correct: number of correct answers
        total: total questions
        streak_days: current streak length
        answer_times: list of seconds per answer (optional, for speed bonus)

    Returns:
        total XP earned
    """
    xp = correct * 10

    # Perfect score bonus
    if correct == total and total > 0:
        xp += 20

    # Streak bonus: +5 per day, max +50
    if streak_days > 0:
        xp += min(streak_days * 5, 50)

    # Speed bonus: +5 per fast answer (<10 sec)
    if answer_times:
        fast_answers = sum(1 for t in answer_times if t < 10.0)
        xp += fast_answers * 5

    return xp


# ---------------------------------------------------------------------------
# STREAK LOGIC
# ---------------------------------------------------------------------------

def update_streak(last_quiz_date: Optional[str], current_streak: int) -> tuple[int, bool]:
    """Update streak based on last quiz date.

    Returns:
        (new_streak, is_continued): new streak value and whether it was continued (not reset)
    """
    today = date.today().isoformat()

    if not last_quiz_date:
        return 1, False

    if last_quiz_date == today:
        return current_streak, True

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if last_quiz_date == yesterday:
        return current_streak + 1, True

    # Streak broken
    return 1, False


# ---------------------------------------------------------------------------
# BADGE CHECKING
# ---------------------------------------------------------------------------

def check_badges(
    total_tests: int,
    current_streak: int,
    level: int,
    percent: float,
    languages_used: int,
    topics_used: int,
    all_fast: bool,
    existing_badges: set[str],
) -> list[str]:
    """Check which new badges have been earned.

    Returns list of newly earned badge keys.
    """
    new_badges = []

    checks = {
        "first_quiz": total_tests >= 1,
        "perfect_score": percent >= 100,
        "streak_3": current_streak >= 3,
        "streak_7": current_streak >= 7,
        "streak_30": current_streak >= 30,
        "tests_10": total_tests >= 10,
        "tests_50": total_tests >= 50,
        "level_5": level >= 5,
        "speed_demon": all_fast,
        "polyglot": languages_used >= 2,
        "explorer": topics_used >= 5,
    }

    for badge_key, condition in checks.items():
        if condition and badge_key not in existing_badges:
            new_badges.append(badge_key)

    return new_badges


# ---------------------------------------------------------------------------
# RESULT COMMENT
# ---------------------------------------------------------------------------

def get_result_comment(theme_key: str, percent: float) -> str:
    """Get themed result comment based on score percentage."""
    theme = THEMES.get(theme_key, THEMES["neutral"])

    if percent >= 90:
        return theme["perfect_msg"]
    elif percent >= 70:
        return theme["good_msg"]
    elif percent >= 50:
        return theme["ok_msg"]
    else:
        return theme["weak_msg"]


def get_theme(theme_key: str) -> dict:
    """Get theme dict by key, fallback to neutral."""
    return THEMES.get(theme_key, THEMES["neutral"])


def format_results_text(
    theme_key: str,
    language: str,
    topic: str,
    correct: int,
    total: int,
    percent: float,
    xp_earned: int,
    streak_days: int,
    level: int,
    xp_total: int,
    new_badges: list[str],
) -> str:
    """Format the full themed results text."""
    theme = get_theme(theme_key)
    lang_flag = "\U0001f1ec\U0001f1e7" if language == "English" else "\U0001f1ea\U0001f1f8"

    comment = get_result_comment(theme_key, percent)

    # XP to next level
    next_level_xp = xp_for_level(level + 1)
    xp_progress = progress_bar(xp_total, next_level_xp)
    level_name = get_level_name(theme_key, level)

    lines = [
        f"\U0001f4ca \u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u0442\u0435\u0441\u0442\u0430",
        f"{lang_flag} {language} | {topic}",
        "",
        f"{theme['xp_emoji']} \u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0445: {correct} \u0438\u0437 {total} ({percent}%)",
        comment,
        "",
        theme["xp_earn"].format(xp=xp_earned),
    ]

    if streak_days > 0:
        lines.append(theme["streak_msg"].format(days=streak_days))

    lines.append(theme["level_msg"].format(level=level_name, xp=xp_total, next_xp=next_level_xp))
    lines.append(xp_progress)

    for badge_key in new_badges:
        emoji, name = BADGES.get(badge_key, ("\U0001f3c5", badge_key))
        lines.append("")
        lines.append(theme["badge_msg"].format(name=f"{emoji} {name}"))

    return "\n".join(lines)


def format_gamification_header(theme_key: str, streak: int, level: int, xp_total: int, badge_count: int) -> str:
    """Format a compact gamification header for history screen."""
    theme = get_theme(theme_key)
    level_name = get_level_name(theme_key, level)
    return (
        f"{theme['streak_emoji']} {streak} \u0434\u043d. | "
        f"\U0001f4c8 {level_name} | "
        f"{theme['xp_emoji']} {xp_total} {theme['xp_name']} | "
        f"\U0001f3c5 {badge_count}/{len(BADGES)}"
    )
