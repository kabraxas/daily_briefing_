# -*- coding: utf-8 -*-
"""
오늘의 일정(Google Calendar) + 할 일(Todoist) 브리핑 텔레그램 봇
- 오늘 일정 / 오늘 할 일(반복 포함) / 이번 주 할 일 3블록
- 반복 할 일: 오늘 마감 회차면 today 필터에 자동 포함 → 🔁 표시
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ────────────── 설정(환경변수) ──────────────
BOT_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID         = os.environ["TELEGRAM_CHAT_ID"]
TODOIST_TOKEN   = os.environ["TODOIST_TOKEN"]
GOOGLE_KEY_JSON = os.environ["GOOGLE_SA_JSON"]
CALENDAR_ID     = os.environ.get("CALENDAR_ID", "primary")

KST  = timezone(timedelta(hours=9))
WEEK = ["월", "화", "수", "목", "금", "토", "일"]


# ────────────── Google Calendar: 오늘 일정 ──────────────
def get_events():
    info = json.loads(GOOGLE_KEY_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar.readonly"])
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now   = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=1)

    res = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    lines = []
    for ev in res.get("items", []):
        title = ev.get("summary", "(제목 없음)")
        s = ev["start"].get("dateTime")
        if s:
            t = datetime.fromisoformat(s).astimezone(KST).strftime("%H:%M")
            lines.append(f" • {t}  {esc(title)}")
        else:
            lines.append(f" • 종일  {esc(title)}")
    return lines


# ────────────── Todoist 공통 ──────────────
def fetch_todoist(filter_str):
    r = requests.get(
        "https://api.todoist.com/rest/v2/tasks",
        headers={"Authorization": f"Bearer {TODOIST_TOKEN}"},
        params={"filter": filter_str},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

def is_recurring(t):
    due = t.get("due") or {}
    return bool(due.get("is_recurring"))

def fmt_task(t, with_date=False):
    p = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}.get(t.get("priority", 1), "P4")
    mark = "🔁 " if is_recurring(t) else ""
    line = f" • [{p}] {mark}{esc(t['content'])}"
    if with_date and (t.get("due") or {}).get("date"):
        line += f"  <i>({t['due']['date']})</i>"
    return line


# ────────────── Todoist: 오늘 할 일 (반복 포함) ──────────────
def get_today_tasks():
    # 반복 할 일도 '오늘 마감 회차'면 여기에 자동 포함됨
    tasks = fetch_todoist("today | overdue")
    tasks.sort(key=lambda t: t.get("priority", 1), reverse=True)
    return [fmt_task(t) for t in tasks]


# ────────────── Todoist: 이번 주 할 일 (오늘 제외) ──────────────
def get_week_tasks():
    # 향후 7일 중 오늘/지난 것 제외 → 앞으로 남은 이번 주 할 일
    tasks = fetch_todoist("7 days & !today & !overdue")
    tasks.sort(key=lambda t: (t.get("due", {}) or {}).get("date", "9999"))
    return [fmt_task(t, with_date=True) for t in tasks]


# ────────────── 텔레그램 발송 ──────────────
def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
    header = f"🌅 <b>오늘의 브리핑</b> ({now.strftime('%Y-%m-%d')} {WEEK[now.weekday()]})"

    try:
        events = get_events()
    except Exception as e:
        print("[calendar] 오류:", e); events = ["(캘린더를 불러오지 못했습니다)"]

    try:
        today_tasks = get_today_tasks()
    except Exception as e:
        print("[todoist today] 오류:", e); today_tasks = ["(할 일을 불러오지 못했습니다)"]

    try:
        week_tasks = get_week_tasks()
    except Exception as e:
        print("[todoist week] 오류:", e); week_tasks = []

    msg = [header, "─" * 15]
    msg.append("\n📅 <b>오늘 일정 (Google Calendar)</b>")
    msg += events if events else [" • 오늘 일정이 없습니다"]

    msg.append("\n✅ <b>오늘 할 일 (Todoist)</b>")
    msg += today_tasks if today_tasks else [" • 오늘 마감 할 일이 없습니다"]

    msg.append("\n🗓 <b>이번 주 할 일 (앞으로 7일)</b>")
    msg += week_tasks if week_tasks else [" • 예정된 할 일이 없습니다"]

    msg.append("\n오늘도 화이팅! 💪")
    send("\n".join(msg))
    print("발송 완료")


if __name__ == "__main__":
    main()
