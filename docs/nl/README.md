# Codex Lifeboat

**Codex met één programma back-uppen, herstellen en overzetten naar een andere Windows-pc.**

[English](../../README.md) · [Beveiliging](../../SECURITY.md) · [Documentatie](ROADMAP.md)

## Downloaden voor Windows

### [Download de nieuwste Codex Lifeboat-release](https://github.com/dkwolf1/Codex-Lifeboat/releases/latest)

Download op de releasepagina uitsluitend dit bestand:

```text
Codex-Lifeboat-Windows-x64-Portable.zip
```

Pak de ZIP uit en start `Codex-Lifeboat.exe`. Installatie, Python en
administratorrechten zijn niet nodig.

> Download niet de automatisch door GitHub gemaakte bestanden **Source code
> (zip)** of **Source code (tar.gz)**. Die zijn alleen voor ontwikkelaars.

Windows SmartScreen kan waarschuwen omdat deze communitybuild niet commercieel
is ondertekend. Controleer voor gebruik het meegeleverde `SHA256.txt`.

## Back-up maken

1. Sluit Codex volledig af.
2. Plaats de USB-stick.
3. Start `Codex-Lifeboat.exe`.
4. Kies **Volledige back-up maken**.
5. Kies daarna **Back-up controleren**.

## Herstellen op een nieuwe computer

1. Installeer Codex, open het eenmaal en meld je aan.
2. Sluit Codex volledig af.
3. Start `Codex-Lifeboat.exe` vanaf de USB-stick.
4. Kies **Volledig herstellen**.
5. Controleer de locatie van de veiligheidskopie en bevestig.
6. Kies daarna **Herstel controleren**.

## Wat wordt meegenomen

- Projectmappen, inclusief `.git`, `.env` en niet-gecommitte bestanden
- Actieve en gearchiveerde lokale chats
- Project- en chatkoppelingen en beschikbare lokale bijlagen
- Skills en overdraagbare Codex-instellingen
- Een consistente SQLite-snapshot en SHA-256-controle

De aanmelding, installatie-id, computeridentiteit, caches, locks en
sandboxgeheimen van de broncomputer worden bewust niet teruggezet.

## Beveiliging

Back-ups zijn niet versleuteld en kunnen broncode, `.env`-bestanden, API-sleutels
en andere vertrouwelijke projectgegevens bevatten. Bewaar de USB-stick veilig.

Codex Lifeboat is een onafhankelijk communityproject en geen officieel OpenAI-product.
