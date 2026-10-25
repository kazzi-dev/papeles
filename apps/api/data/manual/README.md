# Checked source files

Many Philippine government sites block automated downloads (Cloudflare "verify you are human"
pages, 403 errors) or render their content with JavaScript, so `python -m app.ingest` gets
nothing from them. For those agencies we keep a short, checked summary here instead.

## Rules for these files

- Only facts stated on the official page in `Source:`. No blogs, no "commonly required" items.
- Paraphrase; keep numbers, fees, form names and deadlines exactly as the page states them.
- Update `Last checked:` every time you re-check the page.
- If the page doesn't cover something people ask about, say so at the end ("Not covered here").

## Current files

| File | Agency | Source page |
| --- | --- | --- |
| `pagibig-membership.md` | Pag-IBIG Fund | pagibigfund.gov.ph/member_membership.html |
| `psa-serbilis.md` | PSA | psaserbilis.com.ph |
| `nbi-clearance.md` | NBI | clearance.nbi.gov.ph |
| `philsys.md` | PSA (PhilSys) | philsys.gov.ph (maintenance notice) |

These were first written on 2026-10-26 by reading each official page in a browser. Spot-check
them against the source pages before relying on them.

## Still missing (need a person to read the page)

These sites showed a bot-check page even in a browser, so nothing could be checked
automatically. Open each in your own browser and write a file following the rules above:

- **DFA passport** requirements: https://dfa.gov.ph/100-passport-information/246-renewal-of-passport-requirements
  and https://www.passport.gov.ph/
- **LTO** student permit and driver's license requirements: https://lto.gov.ph/
- **PSA PhilSys** registration requirements:
  https://psa.gov.ph/content/registration-philippine-identification-system-philsys

Then add an entry to `../sources.yaml` with `file: manual/<name>.md` and run the ingest again.
