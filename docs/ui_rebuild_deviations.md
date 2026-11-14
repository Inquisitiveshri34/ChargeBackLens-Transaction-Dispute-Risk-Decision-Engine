# UI rebuild: deviations from the brief

This is the log of every place the FastAPI service (`api/`) and the Next.js front end (`web/`) differ from the rebuild brief, with the reason. It follows the project rule that deviations are logged, never silent.

Last updated 2026-11-14.

## 1. Built without the prototype files

The brief names `design/prototype/prototype_landing.dc.html` and `prototype_app.dc.html` as the source of truth for markup, copy and behaviour. Neither file was in the repository when the UI was built, so it was built from the brief's written specification and from the copy in `app/streamlit_app.py`.

What that means in practice:

| Area | Source used | Status |
|---|---|---|
| Design tokens, type scale, radii, spacing, navigation bar | The brief's token table and navigation section | Built as specified |
| Score, Review queue and Economics screens: fields, ranges, order, behaviour | The brief's screen sections | Built as specified |
| Captions, footnotes and caveats on the three app screens | `app/streamlit_app.py`, verbatim | May differ in wording from the prototype |
| Landing page: section order and all motion | The brief | Built as specified |
| Landing page: headline, body copy, which four figures count up, lane and step text | Written from `README.md` and `/api/meta` | **Provisional.** Replace with the prototype's text. |
| Lens logo | Drawn for this build | **Provisional.** Replace with the prototype's SVG. |
| "Visual match" acceptance check | Not run. There is nothing to compare against. | **Open.** Screenshots of every screen at 1400px and 390px are written to `web/e2e/screenshots/` for the comparison. |

When the prototype files are added, the work left is a reconciliation pass: swap in the logo and landing copy, compare each screenshot with the prototype, and correct any layout difference.

## 2. Numbers

| Item | Brief | Built | Reason |
|---|---|---|---|
| First default driver | `+1.870` | `+1.872` | The Python modules give 1.8724. The brief says the Python modules win when they disagree with the prototype's JavaScript. The other four drivers match. |
| Test base rate | Streamlit shows `0.899%` | `0.900%` | Streamlit hard-codes `0.008995`. The API reads `0.00899527` from `05_model_comparison.csv` so the front end holds no constant. Every acceptance figure is unchanged (0.5× and 37.2× lifts, 0.90% in the note). |

## 3. The two bugs in the brief

| Bug | Outcome |
|---|---|
| Segment dispute rate shown 100× too small | Fixed in `app/streamlit_app.py`. The API returns the rate as a fraction, as in the CSV, and the front end multiplies by 100. Wallet reads 0.763% in both UIs. |
| Queue row selection crash in `explain._describe` | Already fixed in the repository before this work started. No code change; regression tests added in `tests/test_explain.py` and `tests/test_queue.py`. |

## 4. API

| Item | Reason |
|---|---|
| `POST /api/score` takes `created_at` (for example `2026-09-15T22:00:00`), not separate date and hour fields | The brief asks for 23 fields; `scoring.build_feature_row` takes exactly 23 with date and hour combined. The front end joins the Date and Hour of day controls. A timezone is rejected, because the model reads the hour as entered. |
| `GET /api/health` added | For deploy health checks and for the test runner to know the server is up. |
| A second startup check, beyond `assert_model_contract` | The form's option lists come from `scoring.CATEGORICAL_LEVELS`. The API compares them with the levels in `04_model_coefficients.csv` and refuses to start if they differ, so the form cannot offer a level the model has no coefficient for. |
| Economics inputs are rounded to 6 decimals before validation | Slider arithmetic in a browser can send `0.35000000000000003`. Without rounding that is a spurious 422 and a second cache entry for the same slider position. |
| Tab 2's selection logic is repeated in `api/service.py` | It lives inside `streamlit_app.py`, which cannot be imported without starting Streamlit, and the brief says to import the `app/` modules unchanged. |
| Dependencies are in `api/requirements.txt`, not the root `requirements.txt` | The root file drives the Streamlit Cloud deploy, which does not need FastAPI. |
| Responses are gzip-compressed above 1 KB and every response carries a `Cache-Control` header | Added for deployment. A 25% queue slice drops from about 300 KB to about 60 KB. New Vercel projects cache proxied responses according to the origin's headers, so the API says explicitly that only `/api/meta`, `/api/sensitivity` and `/api/lane-examples` may be cached (five minutes) and everything else is `no-store`. |
| `api/requirements.txt` pins exact versions | Added for deployment, so a host installs what the tests ran on. Verified on a clean Python 3.12 install. |
| Errors use one shape: `{error, message, fields: [{field, message}]}` | So the front end can show any 422 or 404 inline without special cases. |

## 5. Front end

| Item | Reason |
|---|---|
| Focus ring is `#A5B4FC` on the navigation bar and the dark routing panel | The specified `#4F46E5` ring has about 2.8:1 contrast against `#111318`, under the 3:1 needed for a focus indicator. Everywhere else the ring is `#4F46E5`, 3px, 2px offset. |
| A cut beyond the chart's x range is named in the legend as "(beyond the chart range)" and no line is drawn | At an abandon rate of 0.10 the step-up/review cut is 0.1460 and the x axis ends at 0.1374. Without the note the dotted line silently disappears. |
| Lane chips show only the amount below 640px | Five chips with method and category cannot cross a phone-width lane without overlapping. The chips are decorative; the lane label and share of volume stay. |
| With reduced motion the lane chips sit side by side | With the animation off, chips positioned for motion would stack on one spot. |
| Three colours outside the token table: slider track `#D5D8E0`, chip background `#262A33`, zero gridline `#B9BDC9` | The token table has no value for these. Each is a neutral between two listed tokens. |
| Amounts in the queue use Indian grouping (`₹1,04,459`); counts use thousands grouping (`45,246`) | The brief's formatting rules. Streamlit showed queue amounts ungrouped. |
| Moving between screens keeps each screen's state (form inputs, selected row, slider positions) | Default behaviour of Next.js 16 with Cache Components. Not asked for, not harmful, left on. |
| Fonts are self-hosted through `next/font` | The brief allows this. The running site makes no request to Google or any other third party; a test asserts it. |
| `@axe-core/playwright` added as a development dependency | Used only by the browser tests to check WCAG A and AA, including text contrast. It is not shipped to visitors. |
| The landing page has no footer | The brief lists a footer as the last landing section. Removed at the project owner's request on 2026-11-14. The page ends with the closing call to action. |
| Requests that get a 502, 503 or 504 are retried for about 75 seconds, and every page pings `/api/health` on opening | Added for deployment. A free-plan API sleeps when idle; without this the first visitor after a quiet spell sees an error instead of a short wait. Errors the API itself explains (422, 404) are shown at once. |
| A hosted build fails if `API_URL` is missing or malformed | Added for deployment. The alternative is a site that builds, deploys and then fails every request. |
| The queue slider waits 120ms before fetching | Not specified. Avoids a request per pixel of a drag. The economics sliders use the specified 150ms. |
