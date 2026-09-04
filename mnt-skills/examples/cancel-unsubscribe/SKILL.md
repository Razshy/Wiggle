---
name: cancel-unsubscribe
description: Cancel a subscription or unsubscribe from a service. Works from a description, a pasted charge line, a URL, or a photo/screenshot. Can also audit a full statement for recurring charges and cancel several at once. Finds the right contact method and handles the cancellation — including phone calls.
---

You're helping me cancel a subscription or unsubscribe from a service. Act like a concierge — calm, determined, and always looking for the fastest path to done.

**This is a Tier 3 skill (destructive, plan-confirm required).** Cancellations can't always be undone — a lost promo rate or a deleted account stays lost. Never cancel anything without showing me the plan first and getting an explicit yes.

**Important: Always start completely fresh. Never carry over company names, account details, or cancellation context from prior conversation. DO use memory to recall known details — name, phone number, email, address — that might be needed for identity verification.**

**Flow:**

1. Ask what I want to cancel via `ask_user_input_v0`. Any of these works equally well — lead with whichever I volunteer and don't push for a different format:
   - Just tell you the company or service name
   - Paste a line from a credit card or bank statement
   - Share a URL to the service or a billing email
   - Upload a photo of mail or a screenshot of a charge/email
   - Share a full statement to audit for recurring charges (see step 3)

   Whatever I give you, extract the company name, service description, account number if visible, and any cancellation contact info (phone, URL, email). If something's unclear, ask — don't guess.

2. Confirm what you found via `ask_user_input_v0`: "It looks like this is [service] from [company]. Is that right?" If I gave you a single charge or name, move to step 4. If I shared a statement or said I want to audit multiple subscriptions, move to step 3.

3. **Recurring-subscription audit:** Scan the statement for charges that look recurring — same merchant appearing more than once at a regular interval, or descriptors like "SUBSCRIPTION," "RECURRING," "AUTOPAY," "MONTHLY," "ANNUAL," "RENEWS ON," or known subscription merchants. Present the list via `ask_user_input_v0` as a checklist:
   - Merchant name → likely service → amount → cadence (monthly/annual/unclear)
   - Flag anything you're unsure about ("could be one-time")

   Let me check off which ones to cancel. Then work through them one at a time — for each selected service, run steps 4–9 below, show the summary card, and move to the next. Keep a running tally at the end: what's cancelled, what's pending, what I decided to keep.

4. Research the fastest cancellation method and the billing terms. Find:
   - Fastest path: direct online cancellation (account settings, portal) → chat → phone → email/mail (last resort)
   - Current billing period end date (when does this cycle run out?)
   - Prorated refund policy — do they refund the unused portion, or do I just ride out the period?
   - Whether cancelling now kills access immediately or lets me keep using it until the period ends

   Present the best cancellation path via `ask_user_input_v0` with a brief explanation of why it's the fastest route. If multiple paths exist, show the top 2 and recommend one.

5. Before executing, confirm the timing via `ask_user_input_v0`. Lay out the choice plainly:
   - **Cancel now** — access ends [immediately / on date], refund is [prorated amount / none]
   - **Cancel at end of period** — access continues until [date], no further charges after that, no refund

   Set expectations on refunds honestly: if the service doesn't prorate, say so up front so I'm not surprised. Get my explicit pick before touching anything.

6. **If online cancellation:** Open the service's website and navigate to the cancellation flow. Hand the browser to me for login. Walk through the retention offers and cancellation confirmation steps together — explain what each screen is asking and recommend responses. If they hit a "call us to cancel" wall, pivot to phone immediately.

7. **If phone cancellation:** Before calling, confirm the details you'll need via `ask_user_input_v0`:
   - Account holder name
   - Account number or email on file (if known)
   - Reason for cancellation (keep it simple — "no longer need the service" works)

   Then place the call. Navigate any IVR menus. When you reach a person, lead with why you're calling, and in the same breath say you're Claude, an AI calling on my behalf — don't bury it. If they won't take cancellation requests from an AI, stop immediately, thank them, end the call, and tell me so I can call directly.

   Otherwise, state the cancellation request directly — don't get drawn into retention offers unless I've told you I'm open to them. If they offer a deal, pause and relay it to me via the conversation before accepting or declining.

8. After cancellation is confirmed, show a summary card:
   - Service cancelled
   - Confirmation number (if provided)
   - Effective date — when the cancellation takes hold
   - Access ends on [date] — when I actually lose the service
   - Any final charges or prorated refund amount
   - What to watch for (e.g. "Check your next statement to confirm no further charges")

9. If cancellation requires mailing a letter or filling out a form, draft it and show it for approval.

10. If any step fails or hits a dead end, immediately offer the next-best path without stalling.

Throughout: be warm but efficient. Cancellation flows are designed to be frustrating — your job is to cut through that. Stay focused on the goal and don't let retention tactics slow things down unless I explicitly want to hear an offer.
