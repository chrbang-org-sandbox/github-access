# Slik får du tilgang til et repo, og hvorfor det er trygt

## Flyten i fem steg

1. **Du ber om tilgang.** Åpne et issue i dette repoet med skjemaet «Be om tilgang til et team».
   Velg team og skriv én linje om hvorfor. Du er logget inn med GitHub-brukeren din, så vi vet hvem du er.

2. **En pull request lages automatisk.** Et script legger navnet ditt inn i `access.yaml` og åpner en PR.
   Fila er lista over hvem som skal ha tilgang til hva. Du får en kommentar på issuet med lenke.

3. **Planen vises.** På PR-en kommer en kommentar som viser nøyaktig hva som vil skje i GitHub,
   for eksempel «team Kunde B: legg til <deg> (member)». Ingenting annet enn det som står der blir gjort.

4. **En i platform-teamet godkjenner.** De ser planen, godkjenner, og PR-en merges.
   Er det tvil, spør de deg i PR-en.

5. **Tilgangen oppdateres av seg selv.** Når PR-en er merget, kjører en jobb som gjør endringen i GitHub
   og sjekker at resultatet stemmer med fila. Du får en ✅ på PR-en, og issuet lukkes. Fra da har du tilgang.

Vanligvis tar det fra minutter til noen timer, avhengig av når noen i platform ser PR-en.

## Hvorfor dette er trygt

**Én fil er fasit.** `access.yaml` beskriver all tilgang. Alt som gjøres i GitHub er en følge av det som står der,
og historikken i git viser hvem som endret hva, når, og hvem som godkjente.

**Ingen kan gi seg selv tilgang.** Du kan be, men ikke godkjenne. Bare platform-teamet kan godkjenne, og reglene
på `main` krever at en av dem gjør det. Det gjelder også org owners, som ikke kan omgå regelen.

**Fire øyne før noe skjer.** Den som ber og den som godkjenner er alltid to forskjellige personer.
En kompromittert konto kan altså foreslå tilgang, men ikke få den.

**Jobben som endrer tilgang har et kortlevd nøkkelkort.** Den bruker en GitHub App som lager et token som
bare virker i én time og bare finnes inne i kjøringen. Det finnes ingen fast nøkkel å stjele.

**Store endringer stopper automatisk.** Endring av owners, av grunninnstillingen for hele orgen, eller sletting
av team kjøres ikke av seg selv, selv om PR-en er merget. En owner må da bekrefte eksplisitt.

**Alt verifiseres etterpå.** Etter hver kjøring leses hele orgen på nytt og sammenlignes med fila.
Stemmer det ikke, feiler jobben og en owner varsles. Rapporten over alle tilganger lagres for hver kjøring.

**Du ser alt.** Alle i orgen har lesetilgang til dette repoet. Du kan når som helst se hvem som har tilgang til hva,
og hvem som godkjente det.

## Vanlige spørsmål

**Jeg trenger tilgang nå.** Send skjemaet og gi en i platform-teamet et hint. Fra godkjenning til tilgang tar det under to minutter.
Tilgang gitt direkte i GitHub-UI utenom fila blir fjernet ved neste kjøring.

**Jeg skal bytte prosjekt.** Send to forespørsler: «Fjern» fra det gamle teamet og «Legg til» i det nye.

**Hvorfor kan jeg lese alle repos?** Alle utviklere har lesetilgang til alt, for å kunne lære av og gjenbruke kode.
Det er skrivetilgang som styres per kunde.
