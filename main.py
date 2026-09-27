# -*- coding: utf-8 -*-
"""
브리핑 텔레그램 봇
- 캘린더: 오늘부터 7일(이번 주) 일정을 날짜별로
- Todoist: 예정됨(Upcoming) = overdue + 오늘 + 향후 N일, 날짜별로 (반복 포함)
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ────────────── 설정 ──────────────
BOT_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID         = os.environ["TELEGRAM_CHAT_ID"]
TODOIST_TOKEN   = os.environ["TODOIST_TOKEN"]
GOOGLE_KEY_JSON = os.environ["GOOGLE_SA_JSON"]
CALENDAR_ID     = os.environ.get("CALENDAR_ID", "primary")

DAYS_AHEAD = 7          # 며칠 앞까지 볼지 (오늘 포함 이번 주)
KST  = timezone(timedelta(hours=9))
WEEK = ["월", "화", "수", "목", "금", "토", "일"]


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def daylabel(d):
    """date 객체 → '09-27(일)' / 오늘·내일은 강조"""
    today = datetime.now(KST).date()
    tag = d.strftime("%m-%d") + f"({WEEK[d.weekday()]})"
    if d == today:
        return f"오늘 {tag}"
    if d == today + timedelta(days=1):
        return f"내일 {tag}"
    return tag


# ────────────── Google Calendar: 이번 주 일정 ──────────────
def get_events():
    info = json.loads(GOOGLE_KEY_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar.readonly"])
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now   = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=DAYS_AHEAD)

    res = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    # 날짜별로 그룹핑
    groups = {}
    for ev in res.get("items", []):
        title = esc(ev.get("summary", "(제목 없음)"))
        s = ev["start"].get("dateTime")
        if s:  # 시간 있는 일정
            dt = datetime.fromisoformat(s).astimezone(KST)
            d, line = dt.date(), f"   • {dt.strftime('%H:%M')}  {title}"
        else:  # 종일 일정
            d = datetime.fromisoformat(ev["start"]["date"]).date()
            line = f"   • 종일  {title}"
        groups.setdefault(d, []).append(line)

    lines = []
    for d in sorted(groups):
        lines.append(f" <b>{daylabel(d)}</b>")
        lines += groups[d]
    return lines


# ────────────── Todoist: 예정됨(Upcoming) ──────────────
def fetch_todoist(filter_str=None):
    params = {}
    if filter_str:
        params["filter"] = filter_str
    r = requests.get(
        "https://api.todoist.com/rest/v2/tasks",
        headers={"Authorization": f"Bearer {TODOIST_TOKEN}"},
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def is_recurring(t):
    return bool((t.get("due") or {}).get("is_recurring"))

def get_upcoming_tasks():
    # 필터 없이 '모든 활성 할 일'을 가져온 뒤 파이썬에서 날짜로 거른다
    # (Todoist 필터는 계정 언어에 종속되어 영어 키워드가 안 먹는 경우가 있음)
    tasks = fetch_todoist(None)   # 필터 없음

    today = datetime.now(KST).date()
    limit = today + timedelta(days=DAYS_AHEAD)   # 앞으로 N일까지 (지난 것 포함)

    P = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}
    groups = {}
    for t in tasks:
        due = (t.get("due") or {}).get("date", "")
        if not due:
            continue                      # 마감일 없는 할 일은 제외
        try:
            d = datetime.strptime(due[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d > limit:                     # N일보다 먼 미래는 제외
            continue
        mark = "🔁 " if is_recurring(t) else ""
        p = P.get(t.get("priority", 1), "P4")
        groups.setdefault(d, []).append(
            (t.get("priority", 1), f"   • [{p}] {mark}{esc(t['content'])}")
        )

    lines = []
    for d in sorted(groups):
        label = ("지난 " if d < today else "") + daylabel(d) if d != today else daylabel(d)
        lines.append(f" <b>{label}</b>")
        for _, line in sorted(groups[d], key=lambda x: -x[0]):
            lines.append(line)
    return lines



# ────────────── 텔레그램 ──────────────
def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15,
    )
    if not r.ok:
        print("[telegram] 실패:", r.status_code, r.text)
    r.raise_for_status()


def main():
    now = datetime.now(KST)
    header = f"🌅 <b>브리핑</b> ({now.strftime('%Y-%m-%d')} {WEEK[now.weekday()]})"

    try:
        events = get_events()
    except Exception as e:
        print("[calendar] 오류:", e); events = ["(캘린더를 불러오지 못했습니다)"]

    try:
        tasks = get_upcoming_tasks()
    except Exception as e:
        print("[todoist] 오류:", e); tasks = ["(할 일을 불러오지 못했습니다)"]

    msg = [header, "─" * 15]
    msg.append(f"\n📅 <b>일정 (앞으로 {DAYS_AHEAD}일)</b>")
    msg += events if events else [" • 예정된 일정이 없습니다"]

    msg.append(f"\n✅ <b>할 일 · 예정됨 (앞으로 {DAYS_AHEAD}일)</b>")
    msg += tasks if tasks else [" • 예정된 할 일이 없습니다"]

    msg.append("\n오늘도 화이팅! 💪")
    send("\n".join(msg))
    print("발송 완료")


if __name__ == "__main__":
    main()
