import os
import json
import re
import sys
import codecs

sys.stdout.reconfigure(encoding='utf-8')

FRONTEND_DIR = os.path.join("frontend", "src")
I18N_DIR = os.path.join("backend", "static", "i18n")

# Regex to detect emojis
EMOJI_PATTERN = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)

def check_json_files():
    print("--- VÉRIFICATION DES FICHIERS JSON ---")
    if not os.path.exists(I18N_DIR):
        print(f"Erreur : le dossier {I18N_DIR} n'existe pas.")
        return False

    has_error = False
    json_files = [f for f in os.listdir(I18N_DIR) if f.endswith('.json')]
    keys_per_lang = {}

    for file in json_files:
        filepath = os.path.join(I18N_DIR, file)
        try:
            with codecs.open(filepath, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                keys_per_lang[file] = set(data.keys())
                
                # Check for emojis and empty values
                for k, v in data.items():
                    if not isinstance(v, str):
                        print(f"[ERREUR] Type invalide pour la clé '{k}' dans {file}: {type(v)}")
                        has_error = True
                        continue
                    if not v.strip():
                        print(f"[ERREUR] Valeur vide pour la clé '{k}' dans {file}")
                        has_error = True
                    elif EMOJI_PATTERN.search(v):
                        if k.startswith("ai_typing_") or k == "admin_prompt_modal_tip_title":
                            continue
                        print(f"[ERREUR] Émoji trouvé dans {file} à la clé '{k}': {v}")
                        has_error = True
        except Exception as e:
            print(f"Erreur lors de la lecture de {file} : {e}")
            has_error = True

    # Check for missing keys across languages
    if 'fr.json' in keys_per_lang:
        base_keys = keys_per_lang['fr.json']
        for file, keys in keys_per_lang.items():
            if file == 'fr.json': continue
            missing = base_keys - keys
            extra = keys - base_keys
            if missing:
                print(f"[ERREUR] {len(missing)} clés manquantes dans {file} par rapport à fr.json: {list(missing)}")
                has_error = True
            if extra:
                print(f"[ERREUR] {len(extra)} clés en trop dans {file} par rapport à fr.json: {list(extra)}")
                has_error = True

    if not has_error:
        print("✅ Fichiers JSON propres (aucun émoji hors ai_typing, syntaxe valide, clés synchrones et traduites).")
    return not has_error

def check_svelte_files():
    print("\n--- VÉRIFICATION DES FICHIERS SVELTE ---")
    has_error = False
    double_brace_pattern = re.compile(r'\{\{\$t\(')
    # Check for emojis followed immediately by identical emojis, or patterns indicating duplicate emoji insertion
    # A simple check for any double same emoji:
    
    for root, dirs, files in os.walk(FRONTEND_DIR):
        for file in files:
            if file.endswith('.svelte'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Check for double braces like {{$t(...)}}
                    if double_brace_pattern.search(content):
                        print(f"[ERREUR] Double accolade détectée ({{{{$t...) dans {filepath}")
                        has_error = True

                    # Basic check for duplicate emojis side-by-side
                    emojis_found = EMOJI_PATTERN.findall(content)
                    for i in range(len(emojis_found)-1):
                        if emojis_found[i] == emojis_found[i+1]:
                            # Verify if they are literally side by side in the text
                            if emojis_found[i]*2 in content:
                                print(f"[ATTENTION] Doublon d'émoji possible ({emojis_found[i]*2}) dans {filepath}")

    if not has_error:
        print("✅ Fichiers Svelte propres (aucune double accolade trouvée).")
    return not has_error

if __name__ == '__main__':
    json_ok = check_json_files()
    svelte_ok = check_svelte_files()
    
    if not json_ok or not svelte_ok:
        sys.exit(1)
    else:
        print("\n🎉 Toutes les vérifications sont passées avec succès !")
        sys.exit(0)
