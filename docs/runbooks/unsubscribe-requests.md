# Runbook: unsubscribe replies

Owner: TBD (Jason to assign who monitors support@coachlenz.com)

Some waitlist leads have no usable one-click token. Their email only offers
replying with "unsubscribe". Nothing reads that inbox automatically. A person
does, then calls the admin route below.

Do this within 10 business days of the reply.

## 1. Check the inbox

Read support@coachlenz.com for replies whose subject or body says unsubscribe.
Note the sender address. Do not paste the address into a log, a ticket, or a
commit.

## 2. Call the route

Sign in as a platform admin and send:

```
POST /admin/leads/unsubscribe
{ "email": "<the sender address>" }
```

The match is case-insensitive. A second call for the same address is safe and
changes nothing. An address that is not on the waitlist and not a coach
account returns 200 and changes nothing. A non-admin receives 403.

The route sets the same opt-out as the one-click link: the lead's
unsubscribed_at, a suppression row, and the coach account's marketing opt-in
when that account exists. The log line stores a short hash of the address,
not the address itself.

## 3. Follow-up, not built

An inbound email handler that would do this without a person needs Resend
inbound configuration from Jason. That handler is not in this build.
