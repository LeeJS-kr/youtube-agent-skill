#!/bin/bash
# Called by .github/workflows/yt-comments.yml. Runs every bot; fails the job if any failed.
rc=0
python3 automation/yt_comment_bot.py || rc=1
if [ -n "$IG_ACCESS_TOKEN" ]; then python3 automation/ig_bot.py || rc=1; fi
exit $rc
