# personal-good-reads

Use **Issues** (no edits to this repo). Shorthand: `[r]` = add, `[d]` = done.

## Add

1. New issue → title starts with **`[read]`**
2. Paste links in the description (one per line; optional `url | title`)
3. Submit — list updates here; issue auto-closes

## Mark done

1. New issue → title starts with **`[done]`**
2. Paste the same URL(s) as in **To read**
3. Submit — they go under **Done (recent)**; issue auto-closes

<details>
<summary><strong>Example walkthrough</strong></summary>

**Add two links**

1. Repo → **Issues** → **New issue**.
2. **Title:** `[read] Weekend` (must start with `[read]`).
3. **Description:** paste one URL per line, for example:

```
https://example.com/article-one | Great post
https://example.org/guide
```

4. **Submit** (Create). GitHub Actions runs; this README’s **To read** gains those links; the issue closes with a bot comment.

**Mark one as read**

1. **Issues** → **New issue** again.
2. **Title:** `[done] Read article-one` (must start with `[done]`).
3. **Description:** paste the **exact** URL you finished, e.g. `https://example.com/article-one` (copy from **To read** above).
4. **Submit**. Actions removes it from **To read** and appends a line under **Done (recent)**; the issue closes.

</details>

<details>
<summary><strong>If nothing updates</strong></summary>

- Open **Actions** → **Good reads** and check the latest run (errors show there).
- This workflow file must be on your **default branch** (`main` / `master`) and **Actions** must be enabled.
- After fixing the workflow, open a **new** `[read]` issue (or re-run the failed workflow if GitHub offers it).

</details>

## To read

_Empty — add with a `[read]` issue._

## Done (recent)

_No completed items yet._
