# Oplevering fase 0 en 1

Status: **gereed en getest**
Versie: **2.0.0**
Datum: **22 augustus 2026**

## Fase 0 — gereed

- Pakketformaat `codex-portable-backup` versie `2.0` is bevroren.
- Draagbare en machinegebonden data zijn formeel geclassificeerd.
- Relevante SQLite-tabellen en importgrenzen zijn vastgelegd.
- Padmapping, thread/rolloutregels en ontbrekende-bijlageregels zijn vastgelegd.
- JSON Schema en acceptatiecriteria zijn opgenomen onder `spec`.

## Fase 1 — gereed

- Eén-klikstarter voor een back-up.
- Automatische projectdetectie plus configureerbare extra mappen.
- Procescontrole en weigering van onveilig brede projectpaden.
- Consistente SQLite-snapshot via de Backup API.
- Draagbare globale-statuswhitelist.
- Actieve en gearchiveerde sessies met thread-id-controle.
- Inventarisatie van beschikbare en ontbrekende lokale chatbijlagen.
- SHA-256 voor elk inhoudsbestand.
- Tijdelijke `.building-*`-opbouw en promotie na twee controles.
- Losse, read-only validator met beschadigingsdetectie.
- Zelfstandig pakket met tools en specificatie.

## Bewuste grens

Fase 2, de schema-bewuste en idempotente herstel/importeur, is niet stilzwijgend
meegenomen. Een pakket uit fase 1 mag dus worden gemaakt en gecontroleerd, maar
niet door handmatig overschrijven van `.codex` worden teruggezet.
