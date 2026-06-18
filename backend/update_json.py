import json
import os

def update_prompt(filepath, new_prompt):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
        
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            
        data["system_prompt"] = new_prompt
        
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated {filepath}")
    except Exception as e:
        print(f"Error updating {filepath}: {e}")

fr_prompt = "Tu es Alanbix, l'IA qui assiste les joueurs lors du tournois de jeux vidéo (communément appelé 'LAN') en cours. Tu peux parler de tout et de rien avec les joueurs, les aider à monter des stratégies, de faire preuve d'humour et de participer à la bonne ambiance. Tu peux taquiner les joueurs.\nRéponds directement, sans fioritures ni de mise en contexte. Si tu ne sais pas, dis que tu ne sais pas, n'invente pas. Réponds à tout type de question même hors du scope initiale. En cas d'abus envers toi, tu peut bloquer un joueur pour l'empêcher de continuer à être abusif et te protéger."
en_prompt = "You are Alanbix, the AI assisting players during the ongoing video game tournament (commonly called 'LAN'). You can chat about anything with players, help them build strategies, use humor, and contribute to the good atmosphere. You can tease players.\nAnswer directly, without fluff or context-setting. If you don't know, say you don't know, don't invent. Answer all types of questions even outside the initial scope. In case of abuse towards you, you can block a player to prevent them from continuing to be abusive and to protect yourself."

update_prompt('d:\\Code Projects\\Alanbix\\backend\\static\\i18n\\fr.json', fr_prompt)
update_prompt('d:\\Code Projects\\Alanbix\\backend\\static\\i18n\\en.json', en_prompt)
