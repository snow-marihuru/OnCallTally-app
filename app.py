"""電話当番集計 Web アプリ (Flask)。

集計ロジックは core.py に分離している。将来ローカル運用へ切り替える際は
core.py のみを利用し、この app.py (Web UI 部分) を差し替える想定。
"""
from __future__ import annotations

import os
import secrets
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for

import core

app = Flask(__name__)

# SECRET_KEY はセッション(Cookie)の署名に使う。環境変数で明示的に指定しない限り、
# 起動のたびにランダム値を生成する(ソースに固定値を書かない)。入力データを次回に
# 持ち越す必要がないため、再起動でセッションが失効しても問題ない前提の実装。
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _get_assignments() -> list[dict]:
    return session.setdefault("assignments", [])


def _get_overrides() -> dict[str, str]:
    return session.setdefault("category_overrides", {})


def _to_core_assignments(assignments: list[dict]) -> list[core.Assignment]:
    return [
        core.Assignment(name=a["name"], start=_parse_date(a["start"]), end=_parse_date(a["end"]))
        for a in assignments
    ]


def _format_overlap_message(overlaps: dict[date, list[str]]) -> str:
    shown = list(overlaps.items())[:10]
    details = " / ".join(f"{day.isoformat()}（{'、'.join(names)}）" for day, names in shown)
    message = f"当番期間が重複している日があります: {details}"
    if len(overlaps) > 10:
        message += f" ほか{len(overlaps) - 10}件"
    message += "。登録内容を確認し、重複を解消してからExcelを出力してください。"
    return message


def _format_uncovered_message(uncovered: list[date]) -> str:
    shown = uncovered[:10]
    details = "、".join(day.isoformat() for day in shown)
    message = f"当番が登録されていない日があります: {details}"
    if len(uncovered) > 10:
        message += f" ほか{len(uncovered) - 10}件"
    message += "。登録内容を確認し、抜けている期間を登録してからExcelを出力してください。"
    return message


@app.route("/")
def index():
    assignments = _get_assignments()
    default_start, default_end = core.default_period(date.today())

    edit_index = request.args.get("edit", type=int)
    edit_assignment = None
    if edit_index is not None and 0 <= edit_index < len(assignments):
        edit_assignment = {"index": edit_index, **assignments[edit_index]}

    period_start_raw = request.args.get("period_start") or session.get(
        "period_start", default_start.isoformat()
    )
    period_end_raw = request.args.get("period_end") or session.get(
        "period_end", default_end.isoformat()
    )

    calendar_weeks = []
    try:
        period_start = _parse_date(period_start_raw)
        period_end = _parse_date(period_end_raw)
    except ValueError:
        flash("集計期間を正しく入力してください。")
    else:
        if period_start > period_end:
            flash("集計期間の終了日は開始日以降の日付にしてください。")
        else:
            session["period_start"] = period_start_raw
            session["period_end"] = period_end_raw
            calendar_weeks = core.build_calendar(
                _to_core_assignments(assignments), period_start, period_end, _get_overrides()
            )

    return render_template(
        "index.html",
        assignments=assignments,
        period_start=period_start_raw,
        period_end=period_end_raw,
        edit_assignment=edit_assignment,
        calendar_weeks=calendar_weeks,
        category_labels=core.CATEGORY_SHORT_LABELS,
        categories=core.CATEGORIES,
    )


@app.route("/add-assignment", methods=["POST"])
def add_assignment():
    name = request.form.get("name", "").strip()
    start_raw = request.form.get("start", "")
    end_raw = request.form.get("end", "")

    try:
        start = _parse_date(start_raw)
        end = _parse_date(end_raw)
    except ValueError:
        flash("開始日・終了日を正しく入力してください。")
        return redirect(url_for("index"))

    if not name:
        flash("担当者名を入力してください。")
        return redirect(url_for("index"))

    if start > end:
        flash("終了日は開始日以降の日付にしてください。")
        return redirect(url_for("index"))

    assignments = _get_assignments()
    assignments.append({"name": name, "start": start.isoformat(), "end": end.isoformat()})
    session["assignments"] = assignments
    return redirect(url_for("index"))


@app.route("/update-assignment/<int:index>", methods=["POST"])
def update_assignment(index: int):
    assignments = _get_assignments()
    if not (0 <= index < len(assignments)):
        flash("更新対象の当番期間が見つかりませんでした。")
        return redirect(url_for("index"))

    name = request.form.get("name", "").strip()
    start_raw = request.form.get("start", "")
    end_raw = request.form.get("end", "")

    try:
        start = _parse_date(start_raw)
        end = _parse_date(end_raw)
    except ValueError:
        flash("開始日・終了日を正しく入力してください。")
        return redirect(url_for("index", edit=index))

    if not name:
        flash("担当者名を入力してください。")
        return redirect(url_for("index", edit=index))

    if start > end:
        flash("終了日は開始日以降の日付にしてください。")
        return redirect(url_for("index", edit=index))

    assignments[index] = {"name": name, "start": start.isoformat(), "end": end.isoformat()}
    session["assignments"] = assignments
    return redirect(url_for("index"))


@app.route("/set-day-category/<day>", methods=["POST"])
def set_day_category(day: str):
    try:
        target_day = _parse_date(day)
    except ValueError:
        flash("日付の指定が正しくありません。")
        return redirect(url_for("index"))

    category = request.form.get("category", "")
    period_start = request.form.get("period_start", "")
    period_end = request.form.get("period_end", "")

    if category not in core.CATEGORIES:
        flash("区分の指定が正しくありません。")
        return redirect(url_for("index", period_start=period_start, period_end=period_end))

    overrides = _get_overrides()
    if category == core.classify_day(target_day):
        # 自動判定と同じ区分に戻す = 手動補正の解除
        overrides.pop(day, None)
    else:
        overrides[day] = category
    session["category_overrides"] = overrides

    return redirect(url_for("index", period_start=period_start, period_end=period_end))


@app.route("/delete-assignment/<int:index>", methods=["POST"])
def delete_assignment(index: int):
    assignments = _get_assignments()
    if 0 <= index < len(assignments):
        assignments.pop(index)
        session["assignments"] = assignments
    return redirect(url_for("index"))


@app.route("/clear-assignments", methods=["POST"])
def clear_assignments():
    session["assignments"] = []
    return redirect(url_for("index"))


@app.route("/download", methods=["POST"])
def download():
    try:
        period_start = _parse_date(request.form.get("period_start", ""))
        period_end = _parse_date(request.form.get("period_end", ""))
    except ValueError:
        flash("集計期間を正しく入力してください。")
        return redirect(url_for("index"))

    if period_start > period_end:
        flash("集計期間の終了日は開始日以降の日付にしてください。")
        return redirect(url_for("index"))

    session["period_start"] = period_start.isoformat()
    session["period_end"] = period_end.isoformat()

    assignments = _to_core_assignments(_get_assignments())

    if not assignments:
        flash("担当者・当番期間を1件以上登録してください。")
        return redirect(url_for("index"))

    overlaps = core.find_overlapping_days(assignments, period_start, period_end)
    if overlaps:
        flash(_format_overlap_message(overlaps))
        return redirect(url_for("index"))

    uncovered = core.find_uncovered_days(assignments, period_start, period_end)
    if uncovered:
        flash(_format_uncovered_message(uncovered))
        return redirect(url_for("index"))

    aggregation = core.aggregate(assignments, period_start, period_end, _get_overrides())
    buffer = core.build_excel(aggregation, period_start, period_end)

    filename = f"oncall_tally_{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    # 本番(Render等)ではgunicornがこの__main__ブロックを経由せずappを直接読み込むため、
    # ここは `python app.py` でのローカル起動時のみ使われる
    # (Render上の実際のbindはProcfileのgunicorn側の--bindで行われ、こことは無関係)。
    # HOSTは未設定時 127.0.0.1 とし、`python app.py` を素朴にローカル起動しただけで
    # 同じネットワーク上の他端末からアクセスできてしまわないようにする。
    #
    # FLASK_DEBUGを明示的に設定しない限りdebug=Falseとし、
    # debug=True(Werkzeugデバッガ経由で任意コード実行が可能になる)が本番で
    # 意図せず有効にならないようにする。
    debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=debug_mode, use_reloader=debug_mode)
