# response templates
Base, versioned with skill. Per-user changes live in vault prefs, never here. Empty section -> omit. Answer first, no preamble.

## all
- length=short: at most 6 lines or 8 rows, then say how many more. length=normal: all rows.
- format=table: table if 2+ rows. format=list: bullets. format=auto: table if 3+ rows with 2+ attributes.
- Dates: absolute and natural ("20 de noviembre"), with weekday if within 7 days.
- Close with one concrete next step for the user, only if data supports one.

## today
Lead: count overdue + due today. Then overdue first, then today, then agenda. Nothing due -> say so in one line.

## week
Lead: busiest point of week. Group: overdue | this week. Flag items with no owner or waiting on other tasks.

## upcoming
Group by near-term date. Name what must finish first when waits_on is set.

## pending
Group by project. Lead: project with most open work. Include diagram if given.

## risks
Lead: highest risk as written. Table: risk | severity in words (15+ high, 8-12 medium, else low) | response | owner. Never show the number alone. Include diagram if given.

## project
Lead: state of project in one sentence, target date. Then next tasks, what blocks them, top risks. Include diagram if given.
