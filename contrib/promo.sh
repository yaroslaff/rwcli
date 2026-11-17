#!/usr/bin/env bash
# Bulk-create promo users: PREFIX01..PREFIXnn, all in one squad.
# Edit the settings below, then run without arguments.

COUNT=300                       # how many users
PREFIX=tnnls-promo-31oct-       # username prefix (number is appended)
SQUAD=TnnlsPromo                # squad (group) uuid or name
DAYS=30                         # expires in N days
TRAFFIC_GB=50                   # traffic limit in GB, 0 = unlimited

LOG=/tmp/${PREFIX}$(date +%Y%m%d-%H%M%S).log
exec > >(tee "$LOG") 2>&1       # everything below goes to screen and log

ok=0
fail=0
for n in $(seq -w 1 "$COUNT"); do
    username=${PREFIX}${n}
    echo "$username"
    if rwcli user create "$username" -s "$SQUAD" -d "$DAYS" -g "$TRAFFIC_GB"; then
        ok=$((ok + 1))
    else
        echo "FAILED: $username"
        fail=$((fail + 1))
    fi
done

echo "Done: $ok created, $fail failed. Log: $LOG"
