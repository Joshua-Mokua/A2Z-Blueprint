# Ecobank Official Brand Palette

Source: provided by the Ecobank team on 2026-06-26 (authoritative — overrides the
earlier build colours).

## Official tokens
```
--ecobank-light-blue:  #0082BB
--ecobank-dark-blue:   #005B82
--ecobank-light-green: #BED600
--ecobank-dark-green:  #669438
--ecobank-gray:        #464646
--ecobank-light-gray:  #EDEDED
--ecobank-mid-gray:    #979797
```

Identity is **blue + green** (NO gold).

## Reconciliation with the build (as of 2026-06-26)
The current build used a DIFFERENT palette that must be migrated:
- build cyan `#1797ce`  -> official light-blue `#0082BB`
- build navy `#0e2440`  -> official dark-blue `#005B82`
- build gold `#ffd200`  -> NOT in official set; replace accent usage with the
  greens (`#BED600` / `#669438`) per role (primary action / success / accent).
- grays: adopt `#464646` / `#EDEDED` / `#979797`.

## How to apply (next session — frontend theming task, contained, low-risk)
1. GROUND FIRST: locate where brand colours are defined. Candidates to inspect:
   - `frontend/web/tailwind.config.*` (theme.extend.colors)
   - any CSS variables / `:root {}` in `frontend/web/src/**` (index.css / globals)
   - hardcoded hex literals across components (grep `1797ce`, `0e2440`, `ffd200`)
   - the Streamlit side (`app.py` / `.streamlit/config.toml`) if it carries brand
2. Decide the SEMANTIC mapping (not just hex swap): which official colour is
   primary / primary-hover / accent / success / surface / text / border. Greens
   replace gold's accent role; pick light-blue as primary, dark-blue as deep/nav.
3. Swap tokens in ONE place (config / CSS vars) if the build is tokenised; only
   then chase any hardcoded hex literals.
4. Verify: `pnpm tsc --noEmit` (no type breakage), visual check of dashboard,
   pipeline, credit screens. No backend involvement.

Brand re-theme is INDEPENDENT of the migration, the auth-store fix, and the
integration handoff — schedule it separately.
