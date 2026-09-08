# Setting up your auto-updating NFL predictions site — simple version

Follow these in order. Don't skip any.

---

## Part 1: Create a fresh, empty repository

1. Go to **github.com/new**
2. Repository name: `nfl-predictions`
3. Make sure **Public** is selected
4. Leave everything else unchecked / empty
5. Click **Create repository**

You now have a completely empty repo. Good — we're starting clean.

---

## Part 2: Upload the files (the part that went wrong last time)

**This is the step to be careful with.** On your computer:

1. Unzip `nfl_backend.zip`
2. You'll now have a folder called `nfl_backend`
3. **Open that folder** (double-click into it, so you can see what's inside)
4. Inside, you should see: `app`, `data`, `scripts`, `site`, `tests`,
   `config.py`, `requirements.txt`, `README.md`, `SETUP.md`
5. On a Mac, press **Cmd + Shift + .** (period) right now — this reveals a
   hidden folder called `.github` that you also need to see and select
6. **Select everything** you see inside this folder (Cmd+A / Ctrl+A)
7. Go back to your browser, on the empty repo page click the blue link
   **"uploading an existing file"**
8. Drag your selected items (from step 6) into the upload box

**The test that you did it right:** after uploading, your repo's file list
should show `app`, `data`, `scripts`, etc. **directly** — not one folder
containing all of those. If you see a single folder like `nfl_backend` or
`nfl_backend 2` sitting on its own with everything inside it, that's wrong —
delete the repo (Settings → scroll to bottom → Delete this repository) and
start over from Part 1. It's faster to restart than to fix.

9. Scroll down, click **Commit changes**

---

## Part 3: Let the automation push updates

1. In your repo, click **Settings** (top tab)
2. Left sidebar → click **Actions** → click **General**
3. Scroll to **Workflow permissions**
4. Click **"Read and write permissions"**
5. Click **Save**

---

## Part 4: Turn the website on

1. Still in **Settings**, click **Pages** (left sidebar)
2. Under "Source," choose **Deploy from a branch**
3. Set branch to **main**, folder to **/docs**
4. Click **Save**
5. Wait a minute, refresh this page — a link to your live site appears

---

## Part 5: Run it once now (don't wait for Tuesday)

1. Click the **Actions** tab (top)
2. In the left list, you should now see **"Weekly NFL predictions update"**
   — if you only see "pages-build-deployment" and nothing else, the
   `.github` folder didn't upload; see the troubleshooting note below
3. Click on **"Weekly NFL predictions update"**
4. Click the **Run workflow** button on the right, then click the green
   **Run workflow** button that appears
5. Wait 1-2 minutes, refresh — a green checkmark means it worked
6. Go to your site link from Part 4 — your predictions should be live

---

## If "Weekly NFL predictions update" doesn't show up in Actions

This means the `.github` folder wasn't included in your upload. Fix it
directly on GitHub instead of re-uploading everything:

1. In your repo, click **Add file → Create new file**
2. In the filename box, type exactly (this creates folders automatically):
   ```
   .github/workflows/weekly_update.yml
   ```
3. On your computer, open `nfl_backend/.github/workflows/weekly_update.yml`
   in any text editor, select all, copy
4. Paste it into the big text box on GitHub
5. Click **Commit changes**
6. Go back to the **Actions** tab — it should appear now — then repeat Part 5

---

## From here on

It runs itself every Tuesday morning, automatically, for free. Nothing
else to do unless you want to manually add a note to `data/overrides.json`
for something the automation can't see on its own (see the main README).

## Verifying the new hourly injury check actually works

This feature checks ESPN's free, unofficial injury data every hour and
flags it on the site if your starting QBs' status changes. Because it uses
an *undocumented* API, it needs a real first-run check before you fully
trust it — this could not be tested from the sandbox that built it (its
own network policy blocks all outside sites by default, ESPN included), so
the very first live run is the actual test.

1. Push this update the same way as before (see the main setup steps)
2. Go to **Actions** tab → **"Hourly QB injury check"** in the left list
3. Click **Run workflow** → the green **Run workflow** button
4. Wait ~30 seconds, click into the run that appears
5. Click the **"check-injuries"** job, then expand **"Check QB injury status"**
6. Read the log output:
   - Lines like `[hourly_injury_check] No injury-status changes found this run.`
     mean it ran successfully and just didn't find anything to flag (normal,
     most hours nothing changes)
   - Lines like `Failed to fetch/parse ESPN injuries for KC` mean that
     specific team's request failed — one or two of these occasionally is
     fine (ESPN's API can be flaky), but if EVERY team fails, the endpoint
     or the response shape has likely changed and `app/injury_watch.py`
     needs an update
   - A green checkmark on the run doesn't guarantee data was found, just
     that nothing crashed — check the actual log text to know for sure

