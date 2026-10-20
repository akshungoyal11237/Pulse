# Pulse: your news & markets tracker. Complete beginner guide

**What it does:** a website (works on phone and laptop) showing India / World / Business / Markets & Crypto news (top 10 each), live-ish prices (Nifty, Sensex, US, crypto, forex, gold/oil, your stocks, mutual funds), a "Story so far" for each news item, and an "Explain" button.

**How it updates itself**
- **News + AI summaries: twice a day**, 7:00 AM and 4:00 PM India time.
- **Prices: every hour** (8:30 AM to midnight). This part is completely free (no AI).

**Total time to set up: about 35 minutes** (about 25 minutes if you skip the AI part). You do this once.
Do it on a laptop or computer. It is much easier than on a phone.

---

## What it costs

| Thing | Cost |
|---|---|
| GitHub account, website hosting, the automatic updates | **₹0** |
| Prices, charts, headlines, mutual fund NAVs | **₹0** |
| "Earlier coverage" timeline on each story | **₹0** (works with no AI at all) |
| AI summaries, "Story so far" background, "Explain" | **₹0** using Google's free Gemini key (no payment method was mentioned in Google's free-tier docs) |

**You never have to enter a credit card for this setup.** Do not click "upgrade" or "set up billing" anywhere. If Google ever asks for a card to give you a free key, stop and skip the AI part (Steps 4-5): everything else still works.

Good to know about the free Google key: Google says free-tier prompts may be used to improve its products. Here that is only public news headlines, nothing personal. Google also does not publish fixed free limits for the newest models, so if a run is ever refused the site simply keeps the previous summaries and tries again at the next update.

---

## Before you start (2 minutes)
You need: a laptop, an email address, and a phone number for sign-up verification. Unzip the file you downloaded:
- **Windows:** right-click the zip, click *Extract All*.
- **Mac:** double-click the zip.

You get a folder called `tracker`.

---

## Step 1. Make a free GitHub account (≈5 min)
1. Go to **github.com** and click **Sign up**.
2. Enter your email, a password and a username (your website address will contain this username, so choose something you like, for example `rohit-pulse`).
3. Verify your email with the code GitHub sends you.

## Step 2. Create your project space (≈3 min)
1. Click the **+** at the top right, then **New repository**.
2. Name it **pulse**.
3. Choose **Public** (needed for free hosting; it only holds public news and prices).
4. Leave **Add a README file** unticked.
5. Click **Create repository**.

## Step 3. Upload the files (≈10 min)
1. On the new empty page, click the link **uploading an existing file**.
2. Open your `tracker` folder on your computer. Select **everything inside it except the `workflows-to-paste` folder**: `index.html`, `collect.py`, `config.json`, `requirements.txt`, `README.md` and the `data` folder. Drag them into the browser box.
3. Wait until all files show up, scroll down and click **Commit changes**.

Now add the two "robot" files. They must be created by hand because GitHub hides the folder they live in:
1. Click **Add file**, then **Create new file**.
2. In the name box type exactly: `.github/workflows/update-news.yml`
   (when you type each `/`, GitHub turns it into a folder automatically).
3. On your computer open `workflows-to-paste/update-news.yml` with Notepad / TextEdit, select all, copy, and paste it into the big GitHub text box.
4. Click **Commit changes**, then **Commit changes** again in the popup.
5. Repeat for the second file: name `.github/workflows/update-prices.yml`, pasting the content of `workflows-to-paste/update-prices.yml`.

## Step 4. Get a free Google AI key (≈5 min) *(optional; skip if you want no AI at all)*
1. Go to **aistudio.google.com** and sign in with your normal Google (Gmail) account.
2. Accept the terms if it asks.
3. Click **Get API key**, then **Create API key**. If it asks you to pick a project, choose the default or **Create new**.
4. **Copy the key** (a long string starting with `AIza`) and paste it into a private note for the next step.
5. Do **not** click anything about billing or upgrading.

## Step 5. Give the key to GitHub safely (≈3 min)
1. Go back to your `pulse` repository on GitHub.
2. Click **Settings** (top tab), then **Secrets and variables**, then **Actions** (left menu).
3. Click **New repository secret**.
4. Name: `GEMINI_API_KEY` (exactly, capitals and underscores). Secret: paste your key.
5. Click **Add secret**.

Never paste the key anywhere else or share it. If it leaks, delete it in Google AI Studio and make a new one.

## Step 6. Switch on your website (≈3 min)
1. In the repository click **Settings**, then **Pages** (left menu).
2. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
3. Set **Branch** to **main** and the folder to **/ (root)**, then click **Save**.
4. Wait 1-2 minutes and refresh the page. A box shows **Your site is live at https://YOUR-USERNAME.github.io/pulse/**. That is your address.

## Step 7. Run the first update (≈4 min)
1. Click the **Actions** tab. If you see a green button saying *"I understand my workflows, go ahead and enable them"*, click it.
2. In the left list click **Update news (twice a day)**, then **Run workflow** (right side), then the green **Run workflow** button.
3. Wait 1-3 minutes and refresh. A green tick means it worked. A red cross means something failed: click it, then read the red line and see Troubleshooting below.
4. Do the same for **Update prices (free, hourly)**.
5. Open your website address. You should see real news and prices instead of the placeholder text.

## Step 8. Put it on your phone (≈2 min)
- **Android (Chrome):** open your address, tap the ⋮ menu, then **Add to Home screen**.
- **iPhone (Safari):** open your address, tap the Share button, then **Add to Home Screen**.

**You're done.** From now on it updates itself. Nothing else to run.

---

## Changing things later (no coding)
On GitHub, click a file, then the ✏️ pencil icon, edit, and **Commit changes**.
- **Your stocks:** in `config.json`, under `"watchlist"`, add `["ITC.NS", "ITC"]`. NSE stocks end in `.NS`, BSE in `.BO`, US stocks have no ending.
- **Mutual funds:** under `"mutual_funds"`, add `[scheme_code, "Name"]`. Find a code at `https://api.mfapi.in/mf/search?q=parag%20parikh`. **Please check that the two example funds are the ones you want.**
- **News sources:** add or remove web addresses under `"feeds"`.
- **Update times:** the `cron:` lines in the two workflow files. Times are in UTC, which is 5 hours 30 minutes behind India. `30 1 * * *` is 7:00 AM India.

## Troubleshooting
- **Site shows "Couldn't load data":** you haven't done Step 7 yet, or Pages (Step 6) is still starting. Wait 2 minutes.
- **Red cross in Actions, mentions "permission" or "403":** go to Settings, then Actions, then General, scroll to *Workflow permissions*, choose **Read and write permissions**, Save, and re-run.
- **News appears but no summaries / Explain says "need the AI step":** the key is missing, mistyped, or Google paused the free key for the day. Re-check Steps 4 and 5; it retries at the next update.
- **Story timeline shows "Earlier coverage" but no background:** normal for the first days. The earlier-coverage list needs a few days of saved headlines to fill up.
- **Some prices missing:** Yahoo occasionally blocks or changes things. The page keeps the last good numbers and retries next hour.
- **GitHub says the schedule is paused:** GitHub pauses scheduled runs on a repo that has had no activity for 60 days. The bot's own updates normally count; if it happens, click Actions and re-enable.

## Good to know
- Prices come from Yahoo Finance through an unofficial library and may be delayed about 15 minutes.
- AI summaries can contain mistakes, so every card links to the original article.
- Scheduled runs on GitHub can start 5-15 minutes late at busy times.
- This is for information only, not investment advice.
