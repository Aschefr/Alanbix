# 🌐 Language Management and Internationalisation (i18n)

Alanbix integrates a complete language and translation management system directly from the application. It allows translating the entire user interface, customizing texts, and adding new languages for LAN participants.

---

## ⚙️ i18n Engine Architecture and Operation

### The Double Layer System (Merge)
To reconcile application updates and local customizations made by organizers:
* **Factory Folder (`static/i18n/`)**: Contains the reference translations shipped with the application (`fr.json`, `en.json`, etc.). These files must not be edited manually.
* **User Folder (`data/i18n/`)**: Local persistence folder mounted on the server. On first startup, factory files are automatically copied there (seeding) if they do not exist.
* **Merge Mechanism**: During an API call, the FastAPI backend first loads the reference file (factory) and then overlays (merges) the modifications made by the user present in the user folder. Any edits made from the application are written to `data/i18n/`, ensuring persistence across Docker image updates.

### Reactive Frontend Rendering
* **Svelte Store (`i18nStore.ts`)**: The store manages the asynchronous loading of translations from the merge API (`/api/i18n/{lang}`).
* **Reactive `$t(...)` Helper**: Allows on-the-fly translation of texts with support for dynamic variable interpolation (e.g., `{$t('tournaments.started_by', { name: userName })}`).
* **Language Selector**: A dropdown menu featuring emoji flags is built into the dashboard sidebar. The user's choice is stored in `localStorage` to persist across sessions.

---

## 🖥️ The Language Administration Interface

Accessible via the **Administration > Translation** tab (or the `/dashboard/admin/languages` route).

### 1. Bicolumn Editor
The interface offers a side-by-side comparative view:
* **Left Column**: The reference language (French by default) whose keys are locked.
* **Right Column**: The input fields for the target language currently being edited. Changes are persistently saved by clicking **Save** or via toast confirmation.

### 2. Navigation by Categories
Translation keys are automatically categorized based on their prefix (e.g., `sidebar.*` in "Sidebar", `ia.*` in "AI Assistant", `tournaments.*` in "Tournaments").
* A sidebar allows quick navigation between these sections.
* Badges display the number of missing or empty keys for each category.
* The collapsed/expanded state of categories is preserved locally.

### 3. Real-Time Search and Filtering
A search bar allows instant filtering of keys by:
* Technical key name.
* Source text (reference language).
* Target text (translated language).

---

## 🤖 AI-Assisted Translation (Ollama)

Alanbix leverages the local Ollama AI instance configured on the server to speed up the translation process:

* **Individual Translation**: An AI action button (✨ icon) next to each input field allows automatically translating the source text to the target language using the LLM.
* **Bulk Translation**: The administrator can start an automatic translation of the entire file or only the untranslated keys. The process is handled asynchronously by the AI queue (`ia_queue`), displaying a real-time progress bar and a cancel button.
* **Strict Formatting**: The system prompt forces the model to return only the translated text, keeping interpolation variables intact (e.g., `{count}`) and avoiding superfluous quotes or introductions.

---

## 🔄 Detection and Synchronization of Missing Keys

When a new version of Alanbix is deployed, new translation keys may appear in the reference language (`fr.json`).

* **Automatic Detection**: The system compares the key structure of the reference file with the target file and calculates the number of structurally missing keys (indicated by a red key icon 🔑).
* **Warning Banner**: A warning banner is displayed at the top of the languages interface if a structural desynchronization is detected.
* **Synchronize Button**: Allows injecting all missing keys into the target file with a blank value in one click, ready to be translated manually or via AI (distinguished as structurally missing keys 🔑 vs. untranslated keys ⚠️).
