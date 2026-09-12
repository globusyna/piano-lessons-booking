# Piano Lesson Planner

help me to build front end:Piano Lesson Calendar — Frontend Brief

Derived from piano-calendar-spec.md. This document is everything the frontend needs: screens, states, API shapes, interaction rules, copy, and visual direction.

1. What you're building

Two separate surfaces in one Node app.

Admin (/admin/*) — the teacher. Password-protected session. Desktop-first, used weekly to manage availability, students and packages. Dense, information-rich.

Student (/s/:token) — a parent or adult learner. No login; the URL is the credential. Mobile-first, visited rarely, for one of three reasons: check when my next lesson is, move a lesson, ask for a break. Must be usable by someone who has never seen it before and will not read instructions.

Treat these as two different design problems. The student page should feel calm and nearly empty; the admin should feel like a working tool.

2. Screens

Student — /s/:token (single page, no navigation)

Stacked sections, top to bottom:

Next lesson — the hero. Day, date, time, and lesson number. This is the answer to the question 90% of visits are about, so it should be readable at arm's length.

Upcoming lessons — the rest of the package as a simple list, each with number and date, each with a "Move" action if the lesson is still movable.

Move flow — triggered from a lesson at least 48 hours before it starts. Replaces the list with open slots grouped by day across the next 4 weeks. Picking one sends a request to Andrea; the original lesson stays in place until she approves it from the admin calendar.

Take a break — a quiet link at the bottom, not a button. Opens a confirm dialog explaining what happens (slot released, teacher notified).

States to design: active student with lessons; paused student; flagged student; package finished and awaiting renewal; invalid token.

Admin

Screen Path Purpose Week /admin Default view. Time grid, lessons placed on it, blackouts shaded, open slots empty. Navigate by week. Click any lesson to open a detail popover with Remove. Availability /admin/availability Weekly hours grid (set once, edited rarely) plus a list of blackout ranges with add/remove. Students /admin/students Table: name, status, weekly slot, package progress, copyable personal link. Filter by status. Student detail /admin/students/:id Set weekly slot, open a package, pause/flag, mark invoice sent, full lesson history. Alerts /admin/alerts Packages consumed and awaiting an invoice. Each row has one action: "Mark invoice sent". This is the only place the teacher needs to visit on a schedule.

3. Component inventory

Shared

TimeGrid — the core component. Vertical axis = time in 45-min rows, horizontal = days. Renders three cell types: lesson, blackout, open. Used read-write in admin, read-only in the student move flow.

LessonChip — name (admin) or number (student), time, status colour.

StatusPill — active / paused / flagged.

ConfirmDialog — used for every destructive or semi-destructive action.

Toast — confirmation after mutations. Verb must match the button that triggered it.

Admin only

WeekNav, BlackoutList, StudentTable, PackageProgress (e.g. 7/10 with a thin progress bar), CopyLinkButton.

Student only

NextLessonCard, LessonList, SlotPicker (days as sections, slots as chips).

4. API contracts

The frontend never computes availability, lock state, or eligibility. The server sends booleans; the UI renders them.

// GET /s/:token
{
  "student": { "name": "Anna", "status": "active" },
  "package": { "size": 10, "used": 7, "periodNo": 3 },
  "nextLesson": {
    "id": 412, "seq": 7, "startsAt": "2026-09-15T16:00:00+02:00",
    "canMove": true
  },
  "lessons": [
    { "id": 412, "seq": 7, "startsAt": "...", "status": "scheduled", "canMove": true },
    { "id": 413, "seq": 8, "startsAt": "...", "status": "scheduled", "canMove": true }
  ],
  "canRequestPause": true
}


// GET /s/:token/slots?from=&to=
{ "slots": [ { "startsAt": "2026-09-17T15:15:00+02:00" } ] }


// GET /admin/api/week?start=2026-09-14
{
  "days": [
    {
      "date": "2026-09-15",
      "locked": false,
      "cells": [
        { "type": "lesson", "startsAt": "...", "lessonId": 412,
          "studentName": "Anna", "seq": 7, "size": 10 },
        { "type": "blackout", "startsAt": "...", "note": "Dentist" },
        { "type": "open", "startsAt": "..." }
      ]
    }
  ]
}


Mutations return { ok: true } plus the refreshed object, or { ok: false, error: { code, message } }. Render message directly — the server owns error wording.

Error codes the UI must handle by name: SLOT_TAKEN, DAY_LOCKED, OUTSIDE_WINDOW, STUDENT_PAUSED, STUDENT_FLAGGED, INVALID_TOKEN.

5. Interaction rules

Lock: a day locks at 23:59 local. In the student UI, a lesson on a locked day has no Move action and no explanation clutter — it simply isn't actionable. In the admin UI, locked days look identical; the teacher's actions are never blocked.

Move window: only slots from today through +3 weeks are offered. Never render a disabled slot outside the window — omit it.

Race on move: the slot list can go stale. On SLOT_TAKEN, refetch slots, keep the picker open, and show the message inline above the list rather than as a toast.

Lesson numbers are never renumbered. A moved lesson keeps its seq. Don't sort by number and date interchangeably — sort by date, display the number.

Paused and flagged students see their lessons but no actions. Say what is true and what to do next, without scolding.

6. Copy

Write plainly, sentence case, active voice. A few fixed strings:

Move button: Move lesson → toast Sent request to Andrea

Pause: Ask for a break → dialog body: "Your weekly time will be released and your teacher will be in touch. Your remaining lessons stay on your account."

Empty slot list: "No open times in the next three weeks. Message your teacher to find something."

Package finished: "That was lesson 10 of 10. Your teacher will send an invoice and add the next set."

Invalid token: "This link isn't valid. Ask your teacher for a new one." No further detail.

Admin alerts empty: "Nothing to invoice." Not "No results found."

7. Visual direction

Grounded in the instrument rather than in generic calendar SaaS. The felt red is taken from piano damper felt; the brass from pedals and hardware. Use it on one thing only.

Palette

ink      #1C1A22   text, grid rules, admin structure
paper    #F2F3EF   page background, faintly cool
felt     #7B2D3B   the single accent: booked lessons, primary actions
brass    #B08A3E   package progress only
slate    #5B6068   secondary text, timestamps


Blackouts are a flat 6% ink tint with no border. Open slots are paper with a hairline. Booked lessons are felt. That's the whole grid language — three treatments, no more.

Type Instrument Serif for the next-lesson time and page headings; Atkinson Hyperlegible for everything else. One display face, one text face, clearly distinct. Numbers in the grid are tabular-lining so columns align.

Layout Student page is a single 420px-max column, generously spaced, left-aligned. The next lesson's time is the largest element on the page by a wide margin — everything else is quiet around it. Admin uses full width with the time grid as the fixed structural element; time labels sit in a narrow left gutter and the grid rules do the visual work, so cards and shadows aren't needed anywhere.

Motion One place only: the moved lesson settles into its new position in the list. No section entrance animations, no hover transitions on grid cells beyond a cursor change.

8. Frontend build order

TimeGrid in isolation with fixture data — it's the piece everything else depends on.

Admin week view wired to /admin/api/week, read-only.

Student page: next lesson + list.

Move flow including the SLOT_TAKEN path.

Students table + student detail.

Availability and blackouts.

Alerts.

Non-active states: paused, flagged, package finished, invalid token.

Steps 1–4 are the demo. Build against fixtures first; none of it needs the real backend to look right.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/aada7c01-0f61-4036-959f-7427d1a9fb3a).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
