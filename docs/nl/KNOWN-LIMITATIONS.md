# Bekende grenzen van release 3.4.4

1. OpenAI publiceert geen stabiel importcontract voor de lokale Codex-database.
   De app gebruikt daarom schema-inspectie en moet na toekomstige grote
   Codex-schemawijzigingen opnieuw worden getest.
2. Versiecontrole gebruikt AppX/procesinformatie en, indien beschikbaar, winget.
   Zonder winget of internet verschijnt een waarschuwing en mag de gebruiker
   volgens de productspecificatie doorgaan.
3. De EXE is niet met een commerciële code-signingcertificaat ondertekend.
   Windows SmartScreen kan daarom waarschuwen.
4. Reparsepunten, junctions en symbolische links worden niet gevolgd om lussen en
   onbedoelde kopieën buiten het project te voorkomen; ze worden als waarschuwing
   gerapporteerd.
5. De back-up is niet versleuteld en kan projectgeheimen bevatten.
6. Cloud-only chats of projecten die niet lokaal in de Codex-profieldata staan,
   kunnen alleen door Codex zelf via het account worden gesynchroniseerd.
7. Formaat 2.4 registreert externe projectroots, permanente identiteiten, de
   volledige lokale Codex-inventaris en back-uplijn. Release 3.4.4 ondersteunt nu
   gecontroleerde keuzes voor chatconflicten, projectconflicten en doel-only
   projecten, maar blijft lineaire overdracht en is geen gelijktijdige cloudsync.
8. Na vervanging en expliciete projectverwijdering kunnen verborgen projectgegevens
   op hetzelfde volume blijven zolang een van de twee nieuwste geldige herstelpunten
   ernaar verwijst. Zichtbare archieven worden bewust nooit automatisch opgeruimd.
   Ongeldige of onvolledige herstelpunten blijven voor onderzoek staan en kunnen na
   diagnose handmatige opschoning vereisen.
9. Fase 10.1 toont logische bestandsgroottes. Hardlinks of deduplicatie van een
   package manager (bijvoorbeeld een pnpm-store naast `node_modules`) kunnen op de
   bronschijf fysiek minder ruimte gebruiken, maar een overdraagbare back-up bewaart
   ieder zichtbaar bestand afzonderlijk.
10. Selectie werkt nu per compleet project. Codex-data gaat altijd mee en afzonderlijke
    dependency- of cachemappen worden niet stil verwijderd. Een uitgesloten project
    bewaart zijn chats als projectloze geschiedenis, maar de bestanden zijn niet uit
    die back-up herstelbaar en de oorspronkelijke werkmap kan na herstel ontbreken.
11. Git-conflictuitleg vereist leesbare Git-werkmappen en het Git-programma. Als een
    kant of benodigde geschiedenis ontbreekt, meldt Lifeboat onvoldoende bewijs en
    vallen de volledige bestandshashes en expliciete conflictkeuzes terug als basis.
    Lifeboat haalt ontbrekende geschiedenis nooit automatisch op.
12. Automatische chatuitbreiding gebruikt bewust een strikte bewijsregel: de
    bestaande niet-lege doelrollout en alle relevante metadata moeten na draagbare
    padnormalisatie exact gelijk zijn aan het begin van de langere back-uprollout.
    Gewijzigde records of metadata, ongeldige JSONL, een lege rollout, een langere
    doelchat en iedere andere afwijking vragen een expliciete gebruikerskeuze.
    Lifeboat voert geen algemene chatmerge uit.
13. Versie 3.4.4 is stabiel na bron-, EXE- en uitgepakte-ZIP-tests en een geslaagde
    fysieke Windows 11-route van A naar B en terug. Een fysieke Windows 10-test en
    het lostrekken van een echte USB-stick tijdens schrijven zijn nog niet vastgelegd.
