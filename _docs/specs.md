# Piano Lesson Calendar — Prototype Scope

**Stack:** Node.js + Express (server-rendered EJS or a small React SPA), SQLite via better-sqlite3, Nodemailer for email.
**Users:** one teacher (you), N students. No public signup.

---

## 1. Core rules

| Rule | Definition |
|---|---|
| Lesson length | 45 minutes, on a fixed grid you define |
| Counting | A lesson counts against the package **when it is booked**, not when it is held |
| Numbering | Every lesson displays `3/10` to both teacher and student |
| Day lock | A day locks at 23:59 local time. After lock, only the teacher can remove a lesson |
| Reschedule | Student may move a lesson to any open slot from today through +3 weeks, while the original day is unlocked. Otherwise the lesson is burned (counted, no make-up) |
| Package renewal | When a package is consumed, you get an email. Marking "invoice sent" appends the next 5 or 10 lessons on the same weekly slot |
| Pause | Paused student books nothing; their weekly slot is released |
| Flag | Flagged student cannot book or reschedule; existing lessons stay (per your call) |

**One decision I made for you:** since lessons are counted at booking, a full package is allocated the moment it opens — so the invoice email can't fire at booking time or it would fire instantly. It fires the morning after the **final lesson's date passes**. Change the trigger if you'd rather be billed up front.

---

## 2. Data model

```
teacher_settings   id, admin_password_hash, timezone, notify_email

availability_rule  id, weekday(0-6), start_time, end_time
                   -- your normal working hours

blackout           id, starts_at, ends_at, note
                   -- holidays, one-off unavailability

student            id, name, email, access_token(unique),
                   weekly_day, weekly_time,
                   status(active|paused|flagged),
                   created_at

package            id, student_id, size(5|10), period_no,
                   status(open|consumed|invoiced),
                   created_at, invoiced_at

lesson             id, student_id, package_id, seq,
                   starts_at, original_starts_at,
                   status(scheduled|held|burned|cancelled_by_teacher),
                   created_at
```

A slot is **open** if it falls inside an `availability_rule`, is not inside a `blackout`, has no `lesson` on it, and is in the future.

---

## 3. Teacher screens

1. **Week view** — all lessons, open slots, blackouts. Click a lesson to remove it (works on locked days too).
2. **Availability** — weekly hours grid + add/remove blackout ranges.
3. **Students** — list with status, current package, lessons used (`7/10`), personal link to copy.
4. **Student detail** — set weekly slot, open a package (5 or 10), pause/unpause, flag/unflag, mark invoice sent, full lesson history.
5. **Inbox / alerts** — students whose package is consumed and awaiting invoice.

## 4. Student screen (`/s/:token`)

Single page: their upcoming lessons with numbers, a reschedule button on each unlocked lesson, the grid of open slots for the next 4 weeks, and a "request pause" button. No login, no password.

---

## 5. Routes

```
Teacher (session-protected)
GET  /admin                          week view
POST /admin/availability             replace weekly grid
POST /admin/blackout                 add
DEL  /admin/blackout/:id
GET  /admin/students
POST /admin/students                 create (generates access_token)
POST /admin/students/:id/slot        set weekly day+time
POST /admin/students/:id/package     open package {size: 5|10}
POST /admin/students/:id/status      active|paused|flagged
POST /admin/packages/:id/invoiced    mark sent -> append next package
DEL  /admin/lessons/:id              remove, any day

Student (token in path)
GET  /s/:token                       their page
GET  /s/:token/slots?from&to         open slots
POST /s/:token/lessons/:id/reschedule  {starts_at}
POST /s/:token/pause-request
```

---

## 6. Background job

One nightly cron (`node-cron`, 06:00):
- mark yesterday's `scheduled` lessons as `held`
- any package whose last lesson has passed → `status = consumed`, send you one email listing who needs an invoice

---

## 7. Out of scope for v1

Payments and Stripe, generated PDF invoices, student self-signup, SMS or email reminders to students, multiple teachers, multiple timezones, calendar sync / ICS export, waitlists, trial lessons.

---

## 8. Suggested build order

1. SQLite schema + seed script
2. Availability + blackouts, teacher week view (read-only)
3. Students CRUD + access tokens
4. Package creation → weekly lesson generation with numbering
5. Student page: view lessons + open slots
6. Reschedule with the +3-week window and lock check
7. Pause / flag gating
8. Nightly job + invoice email
9. Teacher lesson removal on locked days

Steps 1–5 give you a usable prototype; 6–9 complete it.
