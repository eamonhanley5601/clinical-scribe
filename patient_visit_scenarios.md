# Patient Visit Scenarios (for demo / testing)

## Logins

| Email | Role | Name | Password |
|---|---|---|---|
| `dr.patel@kyronclinic.demo` | Provider | Dr. Ananya Patel | `ChangeMe123!` |
| `dr.reyes@kyronclinic.demo` | Provider | Dr. Marcus Reyes | `ChangeMe123!` |
| `dr.chen@kyronclinic.demo` | Provider | Dr. Lily Chen | `ChangeMe123!` |
| `admin@kyronclinic.demo` | Admin | Sam Whitfield (Admin) | `ChangeMe123!` |

Paste the transcript text into the "Encounter transcript" box on the New Encounter screen.
Patient identity (first/last name + DOB) is what the backend uses to match a returning patient,
so re-use the exact same name + DOB across a patient's multiple visits to trigger the "returning
patient" behavior (prior-history tool call, referencing earlier diagnoses/treatments).

---

## Patient 1 — Sarah Whitfield (DOB 1978-03-14)

### Visit 1 — New patient, acute low back pain
**Template:** New Patient Evaluation

```
Dr: So what brings you in today?
Pt: My lower back has been killing me for about two weeks now. It started after I was
moving some boxes in the garage.
Dr: Can you point to where exactly it hurts?
Pt: Right here, lower back, and it kind of shoots down into my left leg sometimes.
Dr: Does anything make it better or worse?
Pt: Sitting for a long time makes it worse. Lying flat with my knees up helps a little.
Dr: Any numbness, tingling, or weakness in the leg?
Pt: A little tingling in my foot, especially at the end of the day.
Dr: Any issues with bladder or bowel control?
Pt: No, nothing like that.
Dr: Okay. On exam, there's tenderness over the left paraspinal muscles at L4-L5, positive
straight leg raise on the left at about 40 degrees, reflexes intact, strength 5/5 throughout.
No red flag symptoms. This looks like a lumbar strain with possible mild radiculopathy.
We'll start with NSAIDs, a short course of muscle relaxant, and physical therapy. Avoid
heavy lifting for now. Let's recheck in four weeks, and if it's not improving we'll get
an MRI.
```

### Visit 2 — Returning patient, 6-week follow-up (same name/DOB)
**Template:** Orthopedic Follow-Up

```
Dr: Good to see you again. Last time we talked about your low back pain and started
NSAIDs and PT. How's it going?
Pt: Honestly a lot better. The shooting pain down my leg is pretty much gone. Still a
little stiff in the mornings.
Dr: Any tingling or numbness left?
Pt: No, that went away after the first couple weeks of PT.
Dr: Great. On exam today, straight leg raise is negative bilaterally, strength and
reflexes normal, mild residual tenderness at L4-L5 but much improved from before.
Sounds like the conservative treatment is working well. Let's continue PT for another
three weeks, taper off the muscle relaxant, and you can use NSAIDs as needed. Follow up
only if symptoms flare back up.
```

---

## Patient 2 — Marcus Delgado (DOB 1965-11-02)

### Visit 1 — Post-operative follow-up, lumbar fusion
**Template:** Post-Operative Follow-Up

```
Dr: How are you feeling since the surgery two weeks ago?
Pt: Better than I expected honestly. The leg pain I had before surgery is completely
gone. Incision is a little sore but that's about it.
Dr: Any redness, drainage, or fever?
Pt: No, incision looks clean, no drainage.
Dr: How's your pain management going, still on the oxycodone?
Pt: I've actually cut down to just Tylenol most days.
Dr: Good, that's a great sign this early out. Incision well healed, no signs of
infection. Neuro exam intact, strength 5/5 in both legs, no new numbness. This is
exactly the trajectory we want two weeks post lumbar fusion at L4-S1. Continue to
avoid bending, lifting over 10 pounds, and twisting for now. Start gentle walking,
increase distance as tolerated. See you back in four weeks for X-rays to check fusion
progress.
```

### Visit 2 — Returning patient, physical therapy progress check (same name/DOB)
**Template:** Physical Therapy Progress Check

```
Dr: You're about ten weeks out from your fusion now and started PT a few weeks ago,
how's that going?
Pt: PT has been going well. I can walk about a mile now without much discomfort. Still
get some stiffness by end of day.
Dr: Any new leg pain, numbness, or weakness?
Pt: No, none of that has come back.
Dr: That's consistent with what we saw on your last visit right after surgery, good
continued progress. Core strengthening is coming along, tolerating increased activity
without radicular symptoms returning. Let's advance the PT protocol to include light
resistance training and continue the walking program. Next check-in with X-rays in six
weeks to confirm fusion is solid before we clear you for more strenuous activity.
```

---

## Patient 3 — Priya Nair (DOB 1991-06-22)

### New patient, urgent care, ankle injury
**Template:** Urgent Care Visit

```
Dr: What happened?
Pt: I rolled my ankle playing soccer about two hours ago. It hurts a lot and it's
already swelling up.
Dr: Were you able to walk on it right after?
Pt: I could hobble but it really hurt to put weight on it.
Dr: Which way did it twist?
Pt: Inward, I think, my foot kind of rolled under me.
Dr: On exam there's swelling and ecchymosis over the lateral malleolus, tenderness
over the anterior talofibular ligament, no tenderness over the bony malleoli or
midfoot, negative squeeze test. Ottawa ankle rules are negative so we don't need an
X-ray today. This looks like a grade one to two lateral ankle sprain. We'll get you in
a brace, start RICE protocol, rest, ice, compression, elevation. Use crutches for a few
days as needed, ibuprofen for pain and swelling. Should improve significantly over the
next one to two weeks. Come back if it's not improving or if you can't bear any weight
at all.
```

---

## Patient 4 — Thomas Okafor (DOB 1954-09-08)

### New patient, telehealth, neck pain / cervical radiculopathy
**Template:** Telehealth Visit

```
Dr: Tell me what's been going on with your neck.
Pt: It's been about three weeks now. Started as just neck stiffness but now I've got
this pain that shoots down my right arm into my thumb and index finger.
Dr: Any weakness in the arm or hand?
Pt: A little, I've been dropping my coffee cup more than usual, which isn't like me.
Dr: Any numbness or tingling?
Pt: Yeah, tingling in the same fingers, thumb and index finger on the right.
Dr: Does turning your head a certain way make it worse?
Pt: Turning to the right and looking up makes it worse.
Dr: That's consistent with cervical radiculopathy, likely at the C6 nerve root given the
thumb and index finger involvement and the grip weakness. Since this is a telehealth
visit I can't do a full hands-on exam today, but based on your symptoms I'd like to get
you in for an in-person exam and possibly a cervical MRI if it doesn't improve. In the
meantime let's start a short course of oral steroids and refer you to physical therapy
for cervical traction and strengthening. Avoid activities that reproduce the arm
symptoms. We'll reassess in two weeks.
```

---

## Non-happy-path scenarios (no clinical content)

These are intentionally **not** real clinical encounters, to demonstrate the app's graceful
handling of garbage/empty transcript input — it should refuse to fabricate a note and instead
show a clear message, rather than inventing a SOAP note from nothing.

### Scenario A — Gibberish transcript
**Template:** any

```
asdkjf skdjf lorem ipsum dolor sit amet the quick brown fox jumps over 12345 whatever
this is not a real conversation just random text to see what happens
```

### Scenario B — Off-topic, non-clinical conversation
**Template:** any

```
Dr: Hey, did you catch the game last night?
Pt: Yeah, what a finish. Can't believe they pulled that off in overtime.
Dr: I know, I was yelling at the TV. Anyway, how's the weather been for your trip?
Pt: Actually pretty good, no rain so far. We're headed to the coast this weekend.
Dr: Nice, enjoy that. Let me know how it goes.
```

---

## Other non-happy-path (not transcript-driven)

The second required non-happy-path scenario in the assignment doesn't come from transcript text —
it's demonstrated by an **Admin deactivating a provider's account** (Admin Dashboard → provider
roster → deactivate), then that provider attempting to load/save an encounter or log in: the app
fails closed with a clear "Account has been deactivated" message on every request, not just at
login.
