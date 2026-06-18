import json
import codecs
import os

I18N_DIR = os.path.join("backend", "static", "i18n")

# Load FR as base
with codecs.open(os.path.join(I18N_DIR, 'fr.json'), 'r', encoding='utf-8-sig') as f:
    fr_data = json.load(f)

# Fix EN
en_path = os.path.join(I18N_DIR, 'en.json')
with codecs.open(en_path, 'r', encoding='utf-8-sig') as f:
    en_data = json.load(f)

en_data["admin_toast_ai_blocked"] = "{name} blocked from AI"
en_data["admin_toast_ai_unblocked"] = "{name} AI access restored"

with codecs.open(en_path, 'w', encoding='utf-8-sig') as f:
    json.dump(en_data, f, indent=4, ensure_ascii=False)

# Sync ES with FR keys (just put FR values if missing)
es_path = os.path.join(I18N_DIR, 'es.json')
try:
    with codecs.open(es_path, 'r', encoding='utf-8-sig') as f:
        es_data = json.load(f)
except:
    es_data = {}

for k, v in fr_data.items():
    if k not in es_data:
        es_data[k] = v

# Check if there are keys in ES that are not in FR, and remove them
keys_to_remove = [k for k in es_data if k not in fr_data]
for k in keys_to_remove:
    del es_data[k]

with codecs.open(es_path, 'w', encoding='utf-8-sig') as f:
    json.dump(es_data, f, indent=4, ensure_ascii=False)

print("Fix applied successfully.")
