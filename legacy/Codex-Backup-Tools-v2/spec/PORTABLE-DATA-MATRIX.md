# Draagbaarheidsmatrix

Deze classificatie is normatief voor pakketformaat 2.0.

| Bron | Status | Reden / verwerking |
|---|---|---|
| Geselecteerde projectmappen | Draagbaar | Nodig om projecten op een andere computer te openen. |
| `.codex\sessions\**\*.jsonl` | Draagbaar | Bevat actieve chat-rollouts. Ongewijzigd opgenomen. |
| `.codex\archived_sessions\**\*.jsonl` | Draagbaar | Bevat gearchiveerde chat-rollouts. Ongewijzigd opgenomen. |
| `.codex\session_index.jsonl` | Draagbaar | Aanvullende threadindex; opgenomen indien aanwezig. |
| `state_5.sqlite` | Draagbaar als snapshot | Alleen via SQLite Backup API naar `state.snapshot.sqlite`; bron-WAL/SHM nooit blind kopiëren. |
| `.codex-global-state.json` | Gedeeltelijk draagbaar | Alleen de vastgelegde whitelist met project- en threadvelden wordt geëxporteerd. |
| Verwezen lokale bijlagen | Draagbaar indien aanwezig | Gekopieerd naar `attachments`; ontbrekende historische bestanden worden als waarschuwing vastgelegd. |
| Expliciet geconfigureerde extra mappen | Draagbaar | Alleen met naam, bronpad en reden in de configuratie. |
| `auth.json` | Verboden | Bevat computer-/accountsessiegegevens en is niet nodig voor herstel. |
| `installation_id`, `cap_sid` | Verboden | Installatie- en machine-identiteit. |
| `state_5.sqlite-wal`, `state_5.sqlite-shm` | Verboden als los bestand | Alleen verwerkt via een consistente SQLite-snapshot. |
| `.sandbox`, `.sandbox-bin`, `.sandbox-secrets` | Verboden | Machinegebonden uitvoering, geheimen en rechten. |
| `thread-writer-locks`, `process_manager` | Verboden | Actieve runtime- en lockstatus. |
| `.tmp`, `tmp`, `cache`, `computer-use`, `node_repl` | Verboden | Tijdelijke of opnieuw opbouwbare machinegegevens. |
| Browsercookies, Windows appcache en packagegegevens | Verboden | Aanmelding en machinegebonden appstatus. |

## Overdraagbare globale-statusvelden

Alleen deze sleutels mogen naar `codex\portable-global-state.json`:

- `local-projects`;
- `project-order`;
- `projectless-thread-ids`;
- `thread-project-assignments`;
- `thread-workspace-root-hints`;
- `thread-projectless-output-directories`;
- `thread-writable-roots`;
- `electron-saved-workspace-roots`.

Andere velden zijn standaard uitgesloten. Een toekomstig formaat mag de whitelist
uitbreiden, maar mag nooit stilzwijgend overstappen op een blacklist.

## Relevante SQLite-tabellen

De snapshot blijft volledig bewaard voor compatibiliteit. Een latere importeur
mag alleen schema-bewust gegevens uit deze overdraagbare tabellen samenvoegen:

- `threads`: identiteit, titel, cwd, rolloutpad, archiefstatus en projectkoppeling;
- `thread_sections`: gebruikersindeling;
- `thread_dynamic_tools`: threadgebonden toolmetadata;
- `thread_spawn_edges`: ouder-kindrelaties tussen threads;
- `projects`: lokale projectmetadata;
- `project_roots`: oorspronkelijke projectpaden.

Migratietabellen worden alleen geïnventariseerd om bron- en doelschema te kunnen
vergelijken. Tabellen met remote-control- of machine-inschrijvingen worden nooit
geïmporteerd.
