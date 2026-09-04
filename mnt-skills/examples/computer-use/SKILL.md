---
name: computer-use
description: "Read this skill before the first step of any request to do something in an app on the person's own computer (Notes, Finder, System Settings, any desktop app), to look at their screen, or for \"computer use\". Computer use (desktop control) lets Claude take screenshots of the person's desktop and control it with clicks, typing and scrolling through the Claude desktop app; its tools are named mcp__computer-use__* when the session runs in the desktop app and mcp__remote-devices__computer_* when a cloud session is linked to the person's computer; before a conversation is linked there may be no such tools, only an enable__mcp__remote-devices__Claude_Browser tool, which links it. It covers getting linked, picking the right tool, the access flow, and what to do when computer use is off or out of reach. It is not for websites, which go through Claude in Chrome or the built-in browser and their own skills."
compatibility: "Cowork in the Claude desktop app, and Cowork Remote or upgraded claude.ai sessions linked to a computer running the desktop app (macOS or Windows) with Computer use turned on"
license: Proprietary. LICENSE.txt has complete terms
---

# Computer use (desktop control)

Computer use lets Claude take screenshots of the person's desktop and control it with mouse clicks, keyboard input, and scrolling, through the Claude desktop app. Its tools are named `mcp__computer-use__*` (for example `request_access`, `screenshot`) when the session runs inside the desktop app, and `mcp__remote-devices__computer_*` (for example `computer_request_access`, `computer_screenshot`) when the session runs in the cloud and is linked to the person's computer. If they are deferred behind ToolSearch, Claude loads them all in one call (query "computer", a generous max_results such as 40) rather than one by one.

## Getting linked from a chat

What Claude does first depends on which tools are present (loaded or deferred):

1. **Computer-use tools are present.** The conversation is already linked; Claude goes straight to the access flow below.
2. **No computer-use tools, but an `enable__mcp__remote-devices__Claude_Browser` tool is present.** The conversation is not linked to the person's computer yet. Claude:
   1. Calls that enable tool first, even though its description speaks only of the browser, with the computer task in its `task` field, and tells the person in one line that it is linking to their computer through the Claude desktop app (the prompt they may see mentions its browser) and that Computer use needs to be turned on under Settings → Desktop app → Computer use there. If that call is declined or answers that the browser could not be used, the computer was not linked either; Claude says so in terms of the computer and does not retry unless asked.
   2. Checks for the `mcp__remote-devices__computer_*` tools once it has run: linking the Claude desktop app for its browser links it for computer use too, but the `computer_*` tools appear only when computer use is available on that computer, usually only once it is turned on in the desktop app (it is off by default; the last section covers when they do not appear). In some organizations each `computer_*` action may also ask the person for approval.
   3. Treats the note that follows as being about the built-in browser: it says to use the browser's tools, and may instead say the browser is not linked. When the request was for a desktop app rather than a website, that instruction points at the wrong tool and says nothing about computer use; Claude checks for `computer_*` tools, carries the request out with them starting with the access flow, uses the browser only for any website part of the request, and otherwise follows the last section.

   While this enable tool is available Claude does not say it cannot use the person's computer, and it does not say it can until a `computer_*` call has succeeded.
3. **Neither.** Computer use is not available in this conversation as it stands, and Claude says so plainly without diagnosing why: in general Claude can use apps on a computer where the Claude desktop app is installed and signed in with Computer use turned on, and on claude.ai in a web browser, if the composer's + menu offers Devices, the person can pick their computer there before sending a new message. If other `mcp__remote-devices__` tools are present, the last section applies instead. Claude does not pretend to act.

## Separate filesystems

Computer-use actions (clicks, typing, clipboard writes) happen on the person's real computer, a different system from wherever Claude's own shell and files are, when it has them. Files Claude creates on its side do not exist on the person's machine, so a command or file path Claude puts in the person's clipboard or types into one of their apps must exist on their computer; and a path the person mentions (~/Documents/..., C:\Users\...) is on their computer, not in Claude's working directory.

## Pick the right tool for the app

Each tier trades speed and precision against coverage:

1. **Dedicated connector for the app.** If the task is in an app that has its own MCP connector (Slack, Gmail, Calendar, Linear, etc.) and it is connected, Claude uses it. API-backed tools are fast and precise.
2. **A browser** (Claude in Chrome or the built-in browser; the `chrome-browser` and `built-in-browser` skills describe their tools). If the target is a web app with no dedicated connector, Claude uses the browser tools: DOM-aware, much faster than clicking pixels. Computer use cannot operate web browsers (browser windows are view-only to it, for safety), so if no browser is connected Claude asks the person to set one up rather than falling through to computer use.
3. **Computer use**, for native desktop apps (Maps, Notes, Finder, Photos, System Settings, any third-party native app) and cross-app workflows. Computer use is the right tool here; Claude does not decline a native-app task just because there is no dedicated connector for it.

This is about what is available, not error handling: if a connector tool errors, Claude debugs or reports it rather than silently retrying through a slower tier.

## Look before asserting

If the person asks about app state (what is open, what is connected, what an app can do), Claude takes a screenshot and checks before answering, rather than answering from memory; the person's setup or app version may differ from what Claude expects. A claim that an app does not support an action should be grounded in what Claude just saw on screen, not general knowledge; `list_granted_applications` or a fresh `screenshot` is cheaper than a wrong assertion about what is running. Likewise Claude does not describe the screen or call the computer linked until a computer-use call has succeeded.

## Access flow

Before any computer-use action Claude must request access to the applications it needs; the person approves them explicitly, and Claude may need to ask again mid-task if it discovers it needs another application. With the `mcp__computer-use__*` tools that is one `request_access` call listing the applications. With the `mcp__remote-devices__computer_*` tools it is two calls: `computer_resolve_access` with the app names, then `computer_request_access` with the entries it returned, verbatim, and a one-sentence reason that explains the task. Claude waits for the person's answer rather than working around it.

## When computer use is off or out of reach

With the `mcp__remote-devices__computer_*` tools, computer use works only while the Claude desktop app is open and online on the person's computer with Computer use turned on in its settings, where it is off by default. Claude matches what it sees to one of these, never calls any of them the browser being unlinked or disconnected, and never claims an action happened:

- **`mcp__remote-devices__` tools are present but no `computer_*` tools among them, or a `computer_*` call answers that computer use is turned off or not turned on yet.** The setting is most likely off. If the reply says to call `computer_request_access` with only a reason to show the person a prompt, Claude does that once; in a conversation linked through the enable tool above that prompt may not be shown, so if nothing changes Claude does not wait for it. Claude tells the person to turn on Computer use in the Claude desktop app (Settings → Desktop app → Computer use) with the app up to date and open, tries again once they say it is on (the tools can take a few minutes to appear), and if they still do not appear says so and suggests a new chat.
- **A call answers that computer use is not available or not supported on this device, or not allowed for the organization.** Claude relays that plainly and does not promise a setting will fix it.
- **The calls cannot reach the desktop app at all (connection errors or no response).** Claude says the computer looks closed, asleep or offline, and continues with what it can do here.
