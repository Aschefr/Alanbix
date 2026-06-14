# 📋 Page d'Informations Générale

La page d'informations d'Alanbix (route `/dashboard/info`) centralise les annonces, plannings, règlements de la LAN et liens de téléchargements utiles.

![Page d'Informations](../../../screenshots/alanbix_informations.png)

---

## ✏️ Édition de la Page (WYSIWYG Markdown)

Les administrateurs système disposent d'un éditeur de texte intégré basé sur **EasyMDE**.
* Cet éditeur comporte deux onglets de saisie distincts :
  1. **Contenu Principal (Joueurs)** : S'affiche sur le tableau de bord des participants connectés (planning, règlements, codes WiFi).
  2. **Contenu Projecteur** : S'affiche uniquement lors du défilement automatique du **Mode Spectateur** (ex: les matchs clés de la soirée, les horaires des repas).
* La sauvegarde s'effectue en écrivant dans la table `system_config` sous les clés respectives `info_page_content` et `info_spectator_content`.

---

## 📂 Détection des Chemins Windows (G-45)

Dans le cadre d'une LAN locale, il est fréquent que les organisateurs partagent des dossiers réseau (ex: pour distribuer des installateurs de jeux, des patchs ou des torrents).

* **Le Problème** : Les navigateurs web bloquent par défaut, pour des raisons de sécurité, l'ouverture directe de liens locaux (`file://` ou chemins réseau UNC `\\partage`).
* **La Solution d'Alanbix** :
  1. Le parser Markdown de la page Infos analyse le texte et détecte automatiquement les expressions correspondant à des chemins de répertoires Windows.
     * Chemins UNC réseau : `\\serveur\partage\dossier`
     * Chemins de disques locaux : `C:\Jeux\Alanbix`
  2. Ces textes sont automatiquement encapsulés dans un composant visuel intégrant une icône de dossier (📂).
  3. **Bouton Copie Rapide** : Au clic gauche sur l'un de ces chemins, le système copie automatiquement l'adresse dans le presse-papier de l'utilisateur et affiche une bulle de notification temporaire *"Chemin copié !"*. Le joueur n'a plus qu'à coller le chemin (`Ctrl+V`) dans son explorateur de fichiers Windows pour accéder directement au dossier réseau de la LAN.

---

---

## 📁 Le Gestionnaire de Fichiers Téléchargeables (File Manager)

En complément des liens réseau, Alanbix intègre un gestionnaire de fichiers physiques dédié permettant aux organisateurs d'héberger directement sur le serveur des fichiers utiles (torrents, patchs de jeux, utilitaires de configuration réseau, fichiers `.cfg`).

### Interface d'Administration (Upload & Gestion)
Depuis l'onglet **Administration > Fichiers** :
* **Bouton Sélectionner un fichier / Glisser-Déposer** : Permet de choisir un fichier sur son ordinateur (limité à 100 Mo max par fichier).
* **Bouton "🚀 Téléverser"** : Envoie le fichier au serveur. Le backend applique la fonction de sécurisation `_sanitize_filename` pour supprimer les caractères spéciaux ou espaces problématiques.
* **Sécurité Anti-Écrasement** : Si un fichier avec le même nom existe déjà, le serveur ajoute automatiquement un suffixe incrémental (ex: `patch_1.exe`, `patch_2.exe`) plutôt que d'écraser le fichier d'origine.
* **Bouton Corbeille (✕)** (à côté de chaque fichier) : Supprime définitivement le fichier du stockage du serveur.
* **Bouton de Purge Globale ("Nuke Fichiers")** : Permet de supprimer en masse tous les fichiers téléversés du serveur (après confirmation de sécurité).

### Côté Joueurs (Téléchargement)
* Les fichiers téléversés apparaissent automatiquement sous forme de **cartes cliquables** dans une section dédiée au bas de la page d'informations (`/dashboard/info`).
* Chaque carte indique le **nom du fichier**, sa **taille formatée** (Ko, Mo) et la **date de modification**.
* Un clic gauche télécharge instantanément le fichier en HTTP direct depuis le dossier statique `/data/info_files/` du serveur, même si la LAN est totalement coupée d'Internet.
