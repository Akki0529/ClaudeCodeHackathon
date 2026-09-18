# invoice_processor.py
# author: someone, a while ago
# notes: takes expense csv, applies rules, spits out a summary.
# don't touch the THRESH constants unless you talk to ops.
# this works, please don't break it - vk

import csv
import sys
import os
import datetime

THRESH = 500
THRESH2 = 5000
APPROVAL_THRESH = 2500
PATH = "transactions.csv"


def run(p=PATH):
    f = open(p, "r")
    r = csv.reader(f)
    rows = []
    cnt = 0
    for x in r:
        if cnt == 0:
            cnt = cnt + 1
            continue
        rows.append(x)
        cnt = cnt + 1
    f.close()

    # categorise
    cats = {}
    flagged = []
    needs_approval = []
    total = 0
    by_employee = {}
    by_month = {}

    for x in rows:
        try:
            d = x[0]
            emp = x[1]
            cat = x[2]
            desc = x[3]
            amt = float(x[4])
            cur = x[5]
        except:
            print("bad row: " + str(x))
            continue

        # currency conversion. we only do USD and EUR rn.
        if cur == "EUR":
            amt = amt * 1.08
        elif cur == "GBP":
            amt = amt * 1.26
        elif cur == "USD":
            amt = amt
        else:
            print("unknown currency %s" % cur)
            continue

        # category fixes - some categories changed names last year
        if cat == "Travel-Air":
            cat = "Travel"
        if cat == "Travel-Ground":
            cat = "Travel"
        if cat == "Travel - Air":
            cat = "Travel"
        if cat == "T&E":
            cat = "Travel"
        if cat == "meals":
            cat = "Meals"
        if cat == "Meal":
            cat = "Meals"
        if cat == "client-meal":
            cat = "Meals"

        # bucket
        if cat in cats:
            cats[cat] = cats[cat] + amt
        else:
            cats[cat] = amt

        # employee bucket
        if emp in by_employee:
            by_employee[emp] = by_employee[emp] + amt
        else:
            by_employee[emp] = amt

        # month bucket
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d")
            mkey = dt.strftime("%Y-%m")
        except:
            mkey = "unknown"
        if mkey in by_month:
            by_month[mkey] = by_month[mkey] + amt
        else:
            by_month[mkey] = amt

        # flags
        if amt > THRESH2:
            flagged.append((d, emp, cat, desc, amt))
        if amt > APPROVAL_THRESH and amt <= THRESH2:
            needs_approval.append((d, emp, cat, desc, amt))
        if cat == "Meals" and amt > THRESH:
            flagged.append((d, emp, cat, desc, amt))

        total = total + amt

    # output
    print("==== EXPENSE SUMMARY ====")
    print("total: %s" % total)
    print("")
    print("by category:")
    for k in cats:
        print("  %s: %s" % (k, cats[k]))
    print("")
    print("by employee (top 5):")
    sorted_emp = sorted(by_employee.items(), key=lambda x: x[1], reverse=True)
    i = 0
    for k, v in sorted_emp:
        if i < 5:
            print("  %s: %s" % (k, v))
            i = i + 1
    print("")
    print("by month:")
    for k in sorted(by_month.keys()):
        print("  %s: %s" % (k, by_month[k]))
    print("")
    print("FLAGGED (over %s or meals over %s): %d" % (THRESH2, THRESH, len(flagged)))
    for x in flagged:
        print("  " + str(x))
    print("")
    print("NEEDS APPROVAL (over %s, under %s): %d" % (APPROVAL_THRESH, THRESH2, len(needs_approval)))
    for x in needs_approval:
        print("  " + str(x))

    return total


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(sys.argv[1])
    else:
        run()
