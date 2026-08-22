# Codex Portable Backup Tools 2.0

Deze map bevat fase 0 en fase 1 van de vaste Codex-back-upwerkwijze:

- een bevroren en gedocumenteerd pakketformaat 2.0;
- `Backup-Codex.ps1` en `MAAK-Codex-backup.cmd`;
- een onafhankelijke controle via `Controleer-CodexBackup.ps1` en
  `CONTROLEER-Codex-backup.cmd`;
- echte Python-helperbestanden, dus geen kwetsbare `python -c`-aanroepen;
- een configuratiebestand voor extra projectmappen.

## Normaal gebruik

1. Kopieer deze hele map naar de computer waarvan u een back-up wilt maken.
2. Pas zo nodig `backup-config.json` aan. Automatisch bekende Codex-projectroots
   worden ook zonder configuratie gevonden.
3. Sluit Codex volledig af.
4. Dubbelklik `MAAK-Codex-backup.cmd`.
5. De voltooide back-up verschijnt standaard onder `D:\Codex-Backups`.
6. Dubbelklik daarna `CONTROLEER-Codex-backup.cmd` en geef de pakketmap op.

Een map waarvan de naam met `.building-` begint is nooit een voltooide back-up.
Alleen een pakket met `manifest\package.json`, `backupComplete: true` én een
geslaagde onafhankelijke controle is geldig.

Een extra projectmap voegt u tussen de blokhaken van `projects` toe, bijvoorbeeld:

```json
"projects": [
  {
    "name": "Mijn extra project",
    "path": "%USERPROFILE%\\Documents\\Mijn project",
    "required": true
  }
]
```

Gebruik geen hele schijf of heel gebruikersprofiel als projectpad. De generator
weigert zulke brede paden. Om een willekeurige andere map mee te nemen gebruikt u
`additionalPortablePaths` met dezelfde velden plus een korte `reason`.

## Belangrijke grenzen

Deze fase maakt en controleert back-ups. De veilige importeur/hersteltool hoort
bij fase 2 en is nog niet opgenomen. Zet nooit zelf de volledige `.codex`-map
over een andere installatie heen.

Meer details staan in `spec\PACKAGE-FORMAT-2.0.md` en
`spec\PORTABLE-DATA-MATRIX.md`.
