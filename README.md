# MCP Task Manager

Un gestionnaire de tâches complet exposé via le protocole **MCP (Model Context Protocol)**, persisté en SQLite. Il permet de créer, organiser, filtrer, ordonner et exporter des tâches — avec support natif des projets, des sous-tâches et des tags.

---

## Sommaire

- [Architecture](#architecture)
- [Installation](#installation)
- [Modèle de données](#modèle-de-données)
- [Référence des outils](#référence-des-outils)
  - [Tâches — CRUD](#tâches--crud)
  - [Tâches — Statut](#tâches--statut)
  - [Tâches — Filtrage & Recherche](#tâches--filtrage--recherche)
  - [Tâches — Ordonnancement](#tâches--ordonnancement)
  - [Sous-tâches](#sous-tâches)
  - [Projets](#projets)
  - [Export](#export)
  - [Statistiques](#statistiques)
  - [Opérations en masse](#opérations-en-masse)
- [Exemples d'utilisation](#exemples-dutilisation)
- [Notes techniques](#notes-techniques)

---

## Architecture

```
task-manager/
├── server.py       # Serveur MCP — définition de tous les tools
└── database.py     # Initialisation SQLite et helper de connexion
```

Le serveur est construit avec **FastMCP** et utilise **SQLite** directement (sans ORM). Les données sont stockées dans un fichier `tasks.db` créé automatiquement au premier démarrage.

---

## Installation

### Prérequis

- Python 3.10+
- `mcp`, `pydantic`, `fpdf2`

### Dépendances

```bash
pip install mcp pydantic fpdf2
```

### Démarrage

```bash
python server.py
```

> ⚠️ Ne pas utiliser `print()` dans le code appelant : MCP utilise stdout pour son protocole de communication.

La base de données `tasks.db` est créée automatiquement au premier lancement. L'initialisation est idempotente (`CREATE TABLE IF NOT EXISTS`).

---

## Modèle de données

### Tâche (`Task`)

| Champ | Type | Description |
|-------|------|-------------|
| `id` | `int` | Identifiant unique (auto-incrémenté) |
| `title` | `str` | Titre de la tâche |
| `completed` | `bool` | Statut de complétion |
| `priority` | `"low" \| "medium" \| "high"` | Priorité |
| `tags` | `List[str]` | Liste de labels libres |
| `due_date` | `str \| None` | Date limite au format `YYYY-MM-DD` |
| `description` | `str \| None` | Description longue (texte libre) |
| `project_id` | `int \| None` | Projet associé |
| `parent_id` | `int \| None` | Tâche parente (pour les sous-tâches) |
| `sort_order` | `int \| None` | Position dans l'ordre manuel d'affichage |
| `created_at` | `str` | Horodatage de création |

### Projet (`Project`)

| Champ | Type | Description |
|-------|------|-------------|
| `id` | `int` | Identifiant unique |
| `name` | `str` | Nom unique du projet |
| `description` | `str \| None` | Description libre |
| `color` | `str \| None` | Couleur hexadécimale (ex: `"#FF5733"`) |
| `created_at` | `str` | Horodatage de création |

### Relations

- Une tâche peut appartenir à **un seul projet** (`project_id`).
- Une tâche peut avoir une **tâche parente** (`parent_id`), ce qui en fait une sous-tâche.
- La suppression d'une tâche parente entraîne la suppression en cascade de toutes ses sous-tâches.
- La suppression d'un projet peut soit désassocier les tâches (`unassign_tasks=True`), soit les supprimer (`unassign_tasks=False`).

---

## Référence des outils

### Tâches — CRUD

#### `create_task`

Crée une nouvelle tâche.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `title` | `str` | — | Titre de la tâche *(obligatoire)* |
| `priority` | `"low" \| "medium" \| "high"` | `"medium"` | Priorité |
| `tags` | `List[str]` | `[]` | Labels associés |
| `due_date` | `str \| None` | `None` | Échéance (`YYYY-MM-DD`) |

**Retourne :** `Task`

---

#### `list_tasks`

Retourne toutes les tâches (complétées et ouvertes), sans filtre.

**Retourne :** `List[Task]`

---

#### `delete_task`

Supprime une tâche par son identifiant. Si la tâche a des sous-tâches, elles sont supprimées également.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |

> ⚠️ Opération irréversible.

**Retourne :** `str` (message de confirmation)

---

#### `update_task_title`

Modifie le titre d'une tâche existante.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |
| `title` | `str` | Nouveau titre |

**Retourne :** `Task`

---

#### `update_task_priority`

Modifie la priorité d'une tâche.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |
| `priority` | `"low" \| "medium" \| "high"` | Nouvelle priorité |

**Retourne :** `Task`

---

#### `update_task_tags`

Ajoute ou retire des tags de façon incrémentale (sans écraser les tags existants).

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `id` | `int` | — | Identifiant de la tâche |
| `add_tags` | `List[str]` | `[]` | Tags à ajouter (ignorés s'ils existent déjà) |
| `remove_tags` | `List[str]` | `[]` | Tags à supprimer (ignorés s'ils sont absents) |

**Retourne :** `Task`

---

#### `update_task_due_date`

Modifie ou supprime la date limite d'une tâche.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |
| `due_date` | `str \| None` | Nouvelle échéance (`YYYY-MM-DD`), ou `None` pour supprimer |

**Retourne :** `Task`

---

#### `update_task_description`

Ajoute, modifie ou supprime la description longue d'une tâche.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |
| `description` | `str \| None` | Nouveau texte, ou `None` pour supprimer |

**Retourne :** `Task`

---

### Tâches — Statut

#### `complete_task`

Marque une tâche comme complétée.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |

**Retourne :** `Task`

---

#### `uncomplete_task`

Marque une tâche comme non complétée (rouvre la tâche).

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche |

**Retourne :** `Task`

---

#### `complete_task_with_subtasks`

Marque une tâche **et toutes ses sous-tâches** comme complétées en une seule opération.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Identifiant de la tâche parente |

**Retourne :** `List[Task]` (la tâche parente + toutes les sous-tâches complétées)

---

#### `mark_all_completed`

Marque **toutes** les tâches ouvertes comme complétées.

> ⚠️ Opération globale et irréversible.

**Retourne :** `str` (nombre de tâches affectées)

---

### Tâches — Filtrage & Recherche

#### `list_open_tasks`

Retourne uniquement les tâches non complétées, triées par date de création.

**Retourne :** `List[Task]`

---

#### `list_completed_tasks`

Retourne uniquement les tâches complétées, triées par date de création décroissante.

**Retourne :** `List[Task]`

---

#### `list_tasks_by_priority`

Retourne toutes les tâches triées par priorité décroissante (`high` → `medium` → `low`), puis par date de création.

**Retourne :** `List[Task]`

---

#### `list_tasks_due_today`

Retourne les tâches non complétées dont l'échéance est **aujourd'hui**, triées par priorité.

**Retourne :** `List[Task]`

---

#### `list_overdue_tasks`

Retourne les tâches non complétées dont l'échéance est **dépassée**, triées par date croissante.

**Retourne :** `List[Task]`

---

#### `list_tasks_by_tag`

Retourne les tâches contenant un tag spécifique.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `tag` | `str` | Tag à rechercher |

> ⚠️ La recherche utilise `LIKE` sur le champ CSV — elle peut retourner des faux positifs pour des tags aux noms similaires (ex: `"dev"` peut correspondre à `"devops"`).

**Retourne :** `List[Task]`

---

#### `search_tasks`

Recherche plein texte dans le titre et les tags.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `keyword` | `str` | Mot-clé à rechercher |

**Retourne :** `List[Task]` (triées par date de création décroissante)

---

#### `filter_tasks`

Filtre avancé multi-critères. Tous les paramètres sont optionnels et cumulables (logique `AND`).

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `tag` | `str \| None` | `None` | Filtre sur un tag (recherche `LIKE`) |
| `priority` | `"low" \| "medium" \| "high" \| None` | `None` | Filtre sur la priorité |
| `completed` | `bool \| None` | `None` | `True` = complétées, `False` = ouvertes, `None` = toutes |
| `project_id` | `int \| None` | `None` | Filtre sur un projet |
| `has_due_date` | `bool \| None` | `None` | `True` = avec échéance, `False` = sans |
| `parent_id` | `int \| None` | `None` | `-1` = tâches top-level uniquement, `>0` = sous-tâches d'un parent précis |

Les résultats sont triés par priorité, puis par échéance, puis par date de création.

**Retourne :** `List[Task]`

---

### Tâches — Ordonnancement

#### `set_task_order`

Définit la position manuelle d'une tâche dans l'affichage. Les autres tâches sont automatiquement décalées pour éviter les doublons.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `task_id` | `int` | Identifiant de la tâche |
| `position` | `int` | Position souhaitée (1 = en premier) |

**Retourne :** `Task`

---

#### `list_tasks_ordered`

Retourne toutes les tâches triées par ordre manuel (`sort_order`). Les tâches sans ordre défini apparaissent en dernier.

**Retourne :** `List[Task]`

---

#### `reset_task_order`

Supprime l'ordre manuel de toutes les tâches (remet `sort_order` à `NULL`).

**Retourne :** `str` (message de confirmation)

---

### Sous-tâches

#### `create_subtask`

Crée une sous-tâche liée à une tâche parente. La sous-tâche supporte les mêmes champs qu'une tâche classique.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `parent_id` | `int` | — | Identifiant de la tâche parente *(obligatoire)* |
| `title` | `str` | — | Titre de la sous-tâche *(obligatoire)* |
| `priority` | `"low" \| "medium" \| "high"` | `"medium"` | Priorité |
| `tags` | `List[str]` | `[]` | Labels |
| `due_date` | `str \| None` | `None` | Échéance (`YYYY-MM-DD`) |

> ⚠️ La suppression de la tâche parente entraîne la suppression en cascade de toutes ses sous-tâches.

**Retourne :** `Task`

---

#### `list_subtasks`

Liste toutes les sous-tâches d'une tâche parente, triées par date de création.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `parent_id` | `int` | Identifiant de la tâche parente |

**Retourne :** `List[Task]`

---

### Projets

#### `create_project`

Crée un nouveau projet. Le nom doit être unique.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `name` | `str` | — | Nom unique du projet *(obligatoire)* |
| `description` | `str \| None` | `None` | Description libre |
| `color` | `str \| None` | `None` | Couleur hexadécimale (ex: `"#3B82F6"`) |

**Retourne :** `Project`

---

#### `list_projects`

Liste tous les projets, triés par date de création.

**Retourne :** `List[Project]`

---

#### `delete_project`

Supprime un projet. Le comportement vis-à-vis des tâches associées est configurable.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `id` | `int` | — | Identifiant du projet |
| `unassign_tasks` | `bool` | `True` | `True` = les tâches restent mais perdent leur `project_id` ; `False` = les tâches sont supprimées avec le projet |

**Retourne :** `str` (message de confirmation)

---

#### `assign_task_to_project`

Associe une tâche à un projet, ou la dissocie en passant `project_id=None`.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `task_id` | `int` | Identifiant de la tâche |
| `project_id` | `int \| None` | Identifiant du projet, ou `None` pour dissocier |

**Retourne :** `Task`

---

#### `list_tasks_by_project`

Liste toutes les tâches d'un projet, triées par `sort_order` puis par date de création.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `project_id` | `int` | Identifiant du projet |

**Retourne :** `List[Task]`

---

### Export

#### `export_tasks_json`

Exporte toutes les tâches au format JSON (avec le nom du projet résolu).

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `include_completed` | `bool` | `True` | Inclure les tâches complétées |

**Retourne :** `str` (chaîne JSON prête à écrire dans un fichier `.json`)

---

#### `export_tasks_csv`

Exporte toutes les tâches au format CSV, avec séparateur `;` et encodage `QUOTE_ALL`.

Colonnes exportées : `id`, `title`, `completed`, `priority`, `tags`, `due_date`, `description`, `project`, `parent_id`, `sort_order`, `created_at`.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `include_completed` | `bool` | `True` | Inclure les tâches complétées |

**Retourne :** `str` (chaîne CSV prête à écrire dans un fichier `.csv`)

---

#### `export_tasks_pdf`

Génère un fichier PDF des tâches et le sauvegarde sur le disque. Chaque ligne est colorée alternativement ; la priorité est affichée en couleur (rouge / jaune / vert). Si une tâche a une description, elle apparaît en sous-ligne.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `output_path` | `str` | `"tasks_export.pdf"` | Chemin du fichier PDF à créer |
| `include_completed` | `bool` | `True` | Inclure les tâches complétées |
| `title` | `str` | `"Task Export"` | Titre affiché en haut du PDF |

> ⚠️ Requiert la dépendance `fpdf2` (`pip install fpdf2`). Les caractères en dehors de la plage ASCII standard peuvent poser des problèmes avec les polices Helvetica par défaut — préférer des titres sans caractères spéciaux.

**Retourne :** `str` (chemin du fichier créé)

---

### Statistiques

#### `get_stats`

Retourne un résumé statistique global de toutes les tâches.

**Retourne :** `TaskStats`

```json
{
  "total": 38,
  "completed": 5,
  "open": 33,
  "overdue": 2,
  "by_priority": {
    "high": 14,
    "medium": 16,
    "low": 8
  },
  "by_tag": {
    "backend": 3,
    "design": 4,
    "RH": 2
  }
}
```

---

### Opérations en masse

#### `delete_completed_tasks`

Supprime toutes les tâches ayant le statut complété.

> ⚠️ Opération irréversible.

**Retourne :** `str` (nombre de tâches supprimées)

---

#### `reset_all_tasks`

Supprime **absolument toutes** les tâches, complétées ou non.

> ⚠️ Opération destructive et irréversible. À utiliser avec précaution.

**Retourne :** `str` (message de confirmation)

---

## Exemples d'utilisation

### Créer un projet et y ajouter des tâches

```python
# 1. Créer un projet
project = create_project(
    name="Refonte site web",
    description="Refonte complète du site vitrine",
    color="#3B82F6"
)

# 2. Créer une tâche
task = create_task(
    title="Concevoir les maquettes UI",
    priority="high",
    tags=["design", "figma"],
    due_date="2026-03-15"
)

# 3. Associer la tâche au projet
assign_task_to_project(task_id=task.id, project_id=project.id)
```

---

### Créer des sous-tâches

```python
# Tâche parente (id=1)
sub = create_subtask(
    parent_id=1,
    title="Créer les wireframes basse fidélité",
    priority="high",
    tags=["figma", "wireframe"]
)

# Compléter la tâche et toutes ses sous-tâches d'un coup
complete_task_with_subtasks(id=1)
```

---

### Filtres avancés

```python
# Tâches haute priorité, non complétées, dans le projet 2
filter_tasks(priority="high", completed=False, project_id=2)

# Tâches top-level uniquement (pas de sous-tâches), avec une échéance
filter_tasks(parent_id=-1, has_due_date=True)

# Tâches ouvertes taguées "backend" triées par urgence
filter_tasks(tag="backend", completed=False)
```

---

### Exporter les données

```python
# Export JSON
json_str = export_tasks_json(include_completed=False)
with open("mes_taches.json", "w") as f:
    f.write(json_str)

# Export CSV
csv_str = export_tasks_csv()
with open("mes_taches.csv", "w") as f:
    f.write(csv_str)

# Export PDF
export_tasks_pdf(
    output_path="rapport_taches.pdf",
    title="Rapport du 27 février 2026",
    include_completed=True
)
```

---

### Gérer l'ordre d'affichage

```python
# Mettre la tâche 5 en première position
set_task_order(task_id=5, position=1)

# Afficher les tâches dans l'ordre manuel
tasks = list_tasks_ordered()

# Réinitialiser l'ordre
reset_task_order()
```

---

## Notes techniques

**Stockage des tags** — Les tags sont stockés en base sous forme de chaîne CSV (`"backend,api,sécurité"`). La recherche par tag utilise l'opérateur `LIKE`, ce qui peut produire de rares faux positifs pour des noms de tags très proches. Pour une recherche exacte, il est recommandé de préfixer/suffixer les tags ou d'utiliser des noms distincts.

**Cascade de suppression** — Les sous-tâches sont supprimées explicitement dans le code (sans dépendre du `ON DELETE CASCADE` de SQLite, qui nécessite `PRAGMA foreign_keys = ON` activé à chaque connexion).

**Idempotence** — L'initialisation de la base (`init_db`) est idempotente grâce à `CREATE TABLE IF NOT EXISTS`. Relancer le serveur ne risque pas d'écraser les données existantes.

**Ordre d'affichage** — Les tâches sans `sort_order` défini reçoivent une valeur fictive de `9999` dans les requêtes ORDER BY, ce qui les place en fin de liste après les tâches ordonnées manuellement.

**Thread safety** — Chaque appel à `get_connection()` ouvre une nouvelle connexion SQLite. SQLite gère le verrouillage des écritures en mode WAL si nécessaire ; pour des usages intensifs en parallèle, une gestion de pool de connexions serait à envisager.
