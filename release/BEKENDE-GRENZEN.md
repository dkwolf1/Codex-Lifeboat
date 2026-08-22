# Bekende grenzen van release 3.0.0

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
