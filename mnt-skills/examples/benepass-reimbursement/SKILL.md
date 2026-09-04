---
name: benepass-reimbursement
description: "Submit expense reimbursements through Benepass (app.getbenepass.com). For users whose employer uses Benepass as their benefits platform. Handles login, benefit selection, form filling, receipt upload, and submission. Requires browser/computer-use capabilities."
---

# Benepass Reimbursement Skill

Automate the complete Benepass reimbursement flow — from login through submission — using browser automation, Gmail integration for verification codes, and file upload for receipts.

---

## Prerequisites

- Enable **browser access** (computer tool) for navigating Benepass
- Enable **code execution & file creation** — required for saving and uploading receipt files
- Configure **Gmail MCP** for fetching email verification codes
- Determine the email via Gmail MCP; if Gmail access is unavailable, ask for it
- Obtain a receipt image (screenshot, photo, or PDF)

---

## Step 1: Extract Receipt Details

Before navigating to Benepass, extract the key details from the receipt image or message:

- **Amount** (e.g., $84.99)
- **Merchant** (e.g., Verizon, DoorDash, Lyft)
- **Memo/Note** — apply the provided memo, or default to a short description (e.g., "Home wifi", "Lunch", "Ride to office")
- **Benefit category** — select the specified category; infer from context when confident, otherwise prompt for clarification (see Step 4)

---

## Step 2: Login to Benepass

### 2a. Navigate and enter email

```
Navigate to: https://app.getbenepass.com
```

- Click the email input field and type the email address
- Two login options appear: **"Log in with G-Suite"** and **"Log in with Email Code"**
- Click **"Log in with Email Code"**

### 2b. Fetch verification code from Gmail

Wait for the "Enter verification code" prompt with 6 input boxes to appear.

Fetch the code via Gmail MCP:

```
Gmail search query: "from:benepass verification code"
maxResults: 1
```

- Extract the 6-digit code from the email snippet (look for "Your verification code is: XXXXXX")
- Type the 6-digit code into the verification input — the page auto-submits after all 6 digits are entered
- Wait 3-5 seconds for the dashboard to load

### 2c. Verify login success

Verify the dashboard loads with a greeting, account balances, and insights cards to confirm login success.

**Important**: Handle expired verification codes as follows:

- Click "Didn't receive it? Resend" on the verification page
- Wait 5 seconds, then search Gmail again for a newer code

---

## Step 3: Start Reimbursement

- Click the **"Get reimbursed"** button in the left sidebar
- Wait for the reimbursement form to load with two sections:
  1. **Select benefit** (dropdown)
  2. **Enter details** (amount, merchant, note, receipt)

---

## Step 4: Select Benefit

- Click the **"Select benefit"** dropdown
- Select the specified category; infer from context when confident, otherwise prompt for clarification
- Read the available benefit options directly from the dropdown — categories vary by employer
- Check that the displayed balance for the selected benefit covers the reimbursement amount

---

## Step 5: Fill in Details

### Amount field

**CRITICAL**: Clear any pre-populated value from the amount field before entering the correct amount.

- Triple-click the amount field to select any existing value
- Type the correct amount (e.g., `84.99`)
- Do NOT include the `$` sign — enter just the number

### Merchant field

- Click the merchant input field
- Type the merchant name (e.g., `Verizon`, `DoorDash`, `Lyft`)

### Note field (Optional but recommended)

- Click the note input field
- Type the memo (e.g., `Home wifi`, `Lunch`, `Ride to office`)

---

## Step 6: Upload Receipt

**CRITICAL**: The file input is a **hidden element** with `id="fileInput"`. The visible drop zone is not clickable — use the hidden input instead. If no element with `id="fileInput"` is found, search for any `<input type="file">` on the page.

1. Use `read_page` with `filter: interactive` to find the file input element
2. Look for: `<input id="fileInput" class="hidden" type="file">`
3. Use the `upload_file` tool with the ref for that hidden input:

```
upload_file:
  file_path: <path to the receipt file>
  ref: <ref for fileInput>
```

4. After upload, verify:
   - The **Receipt** label is no longer red (was red before upload)
   - A "Files uploaded" section appears showing the filename and size
   - A thumbnail preview of the receipt is visible

---

## Step 7: Submit

- Scroll down to see the **"Submit reimbursement"** button
- **Before clicking submit**, present a summary for confirmation:
  - Benefit category
  - Amount
  - Merchant
  - Memo/note
  - Receipt filename
  - Remaining benefit balance after this submission
- Wait for explicit approval before proceeding
- Click **"Submit reimbursement"**
- Wait 3 seconds for processing

### Verify submission success

After submission, the page redirects to an expense details view showing:

- **State**: Pending
- **Payment method**: Reimbursement
- **Benefit**: The selected benefit name
- **Payout progress**: Outstanding amount = the submitted amount

Report the confirmation.

---

## Troubleshooting

### Session expired

Handle session expiration by restarting from **Step 2** (login) when errors occur or the page redirects to login.

### Verification code not working

Handle expired verification codes: click "Didn't receive it? Resend", wait a few seconds, then re-search Gmail for a newer code. Ensure the **most recent** email is fetched (use `maxResults: 1` with default sort).

### Amount field quirk

Always triple-click the amount field to select all existing text before typing the new amount — this avoids concatenation (e.g., `32184.99`).

### Upload not registering

If the receipt upload does not appear to work:

1. Re-read the page with `read_page` to find the `fileInput` ref
2. If `fileInput` is not found, search for any `<input type="file">` element
3. Retry uploading with `upload_file` using the correct ref
4. Verify the "Files uploaded" section appears after upload

### Benefit balance too low

If the selected benefit lacks sufficient balance, report the issue and ask whether to use a different benefit category.
