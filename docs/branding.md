# MW branding on Fava

Fava is MIT-licensed open source, so restyling it as "MW Books" is fully allowed.
Two ways to do it, in order of preference:

**1. Light-touch theme (recommended).** Fava supports extensions that ship their own
CSS/JS/templates. A tiny `mw_theme` extension can set the MW color palette, logo,
and "MW Books" title without touching Fava's code. Survives every `pip install -U fava`.

**2. Full fork.** Copy the Fava repo, rebrand everything. NOT recommended: we'd be
maintaining a fork forever and drift away from upstream fixes. Only worth it if we
someday need behavior Fava's extension API can't reach.

Decision 2026-08-11 (Webster): brand it. Start with option 1; build after the
Step 0 survey — data lanes before paint.
