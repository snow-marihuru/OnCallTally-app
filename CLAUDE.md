# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

OnCallTally-app は、電話当番（オンコール）表から集計期間内の当番日数を「平日／土曜日／日祝日」区分別に人ごとへ自動集計し、Excel（.xlsx）で出力するWebアプリ。給与計算（担当日数のカウント）の手作業・ミスをなくすことが目的。単価計算は行わず、日数集計のみを担う。将来的にはWeb UIを外してローカル運用へ切り替える構想があるため、集計ロジックとUIを分離した構成にしている。

給与締めは毎月15日のため、集計期間は暦月ではなく「前月16日〜当月15日」を1サイクルとして扱う（例: 7/16〜8/15）。

## よく使うコマンド

```bash
# 仮想環境の作成・依存インストール（初回のみ）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 開発サーバー起動（http://127.0.0.1:5000）
.venv/Scripts/python.exe app.py
```

自動テストは未整備。動作確認は Flask の test_client を使い、対話的に `app.py` のルートと `core.py` の集計関数を呼び出して行う（`python -c` で core.aggregate / core.build_excel / app.test_client() を直接叩くのが早い）。

## アーキテクチャ

- **core.py** — 集計ロジック本体。Web UIに依存しない純粋なロジックとして分離している。
  - `classify_day(date)` : 日付を `weekday` / `saturday` / `sunday_holiday` に自動分類。祝日判定は `jpholiday.is_holiday()`。日曜は祝日判定より優先して `sunday_holiday` に含める。
  - `resolve_category(date, overrides)` : `classify_day` の自動判定に対し、`overrides`（ISO日付文字列 → 区分名の辞書）に手動指定があればそちらを優先する。会社の公休日（本来は平日／土曜だが日祝日扱いにしたい日）や、祝日だが平日扱いにする日など、自動判定と実態がずれるケースを人手で補正するための仕組み。`aggregate` と `build_calendar` はいずれもこの関数経由で区分を決定する。
  - `aggregate(assignments, period_start, period_end, overrides=None)` : 担当期間を集計期間でクリップしてから日毎に区分・積算する。担当期間が集計期間の外にはみ出す分はカウントしない。人名（`Assignment.name`）でグルーピングするため、同一人物の複数期間登録は自動的に1行にまとまる。
  - `find_overlapping_days(assignments, period_start, period_end)` : 集計期間内で同じ日に複数の当番期間（同一人物の重複登録も含む）が重なっている日を検出する。日数の二重カウント防止用で、`app.py` の `/download` はここで重複が見つかると Excel を出力せずエラーを表示する。
  - `find_uncovered_days(assignments, period_start, period_end)` : 集計期間内でどの当番期間にも含まれない空白日を検出する。当番の登録漏れ防止用で、こちらも見つかると `/download` は Excel を出力しない。
  - `build_excel(aggregation, period_start, period_end)` : openpyxl で集計結果を .xlsx（BytesIO）として生成する。担当者ごとの行に加え、末尾に区分別・合計日数の「合計」行を出力する。
  - `build_calendar(assignments, period_start, period_end, overrides=None)` : Excel出力前に画面上で「誰がいつ当番か」を目視確認できるよう、集計期間全体を1つの連続したカレンダー（週単位の行のリスト、月曜始まり）として組み立てる。月をまたぐ期間（例: 7/16〜8/15）でも表を分割せず、period_start を含む週の月曜日から period_end を含む週の日曜日までを並べる。各セルは実日付・区分（overrides適用後）・上書きフラグ（`overridden`）・担当者名一覧を持ち、期間外の日は `in_period=False` になる（月・グリッド単位の分割はしていない）。
  - `default_period(today)` : 「前月16日〜当月15日」サイクルのうち today が含まれる進行中の期間を返す（画面の初期値に使用）。
  - **jpholiday は祝日データをライブラリ内部に保持しているため、法改正等に対応するには年1回程度ライブラリ本体をアップデートすること**（コード内にも同旨のコメントあり）。
- **app.py** — Flask による Web UI。ルーティングとフォーム処理のみを担当し、集計そのものは core.py に委譲する。
  - 担当者・当番期間の登録一覧は DB を使わず Flask セッション（`session["assignments"]`）に保持する簡易実装。区分の手動上書きも同様に `session["category_overrides"]`（ISO日付文字列 → 区分名）に保持する。いずれも永続化はしておらず、セッションが切れると消える。
  - `/add-assignment`, `/update-assignment/<index>`, `/delete-assignment/<index>`, `/clear-assignments` : 登録一覧の追加・更新・削除・全クリア。編集は一覧行の「編集」ボタン（`GET /?edit=<index>` を送信するフォーム。削除ボタンと見た目を揃えるため `<a>` ではなくボタン付きフォームにしている）でトップページの登録フォームに既存値を読み込み、同じフォームから `/update-assignment/<index>` へ送信する形（専用の編集ページは持たない）。
  - `/set-day-category/<day>` : カレンダーの区分プルダウン（`onchange="this.form.submit()"` で選択時に自動送信）から呼ばれる。選択区分が自動判定（`core.classify_day`）と同じなら overrides から該当日を削除（手動補正の解除＝自動判定に戻す）、異なれば overrides に保存する。処理後は period_start / period_end を維持したまま `GET /` にリダイレクトする。
  - `GET /` (`index()`) : クエリパラメータ `period_start` / `period_end`（未指定ならセッション→デフォルトの順で補完）を集計期間として解釈し、`core.build_calendar` にセッションの overrides を渡してカレンダープレビューを生成する。有効な期間であればセッションにも保存する。
  - `/download` : 集計期間を受け取り、`core.find_overlapping_days` → `core.find_uncovered_days` の順でエラーチェックした後、問題なければ `core.aggregate`（セッションの overrides を渡す）→ `core.build_excel` を呼び出して .xlsx を `send_file` で返す。
- **templates/index.html** / **static/style.css** — 単一ページのフォーム＋一覧＋カレンダー確認＋ダウンロードUI。日付入力は HTML5 の `<input type="date">` を利用し、手入力とカレンダーUIの両方に自然に対応させている。登録フォームは `edit_assignment`（`app.py` の `index()` がクエリパラメータ `edit` から算出）の有無で「登録モード」と「編集モード」を切り替える。集計期間フォームは1つの `<form method="get">` に「カレンダーで確認」（GET / を再表示）と「Excelダウンロード」（`formmethod="post" formaction="/download"` でオーバーライド）の2つの送信ボタンを持たせ、同じ日付入力欄を共有している。カレンダーは区分ごとに背景色を変え（`td.weekday` / `td.saturday` / `td.sunday_holiday`）、手動上書きされたセルは `overridden` クラスで破線枠を付け、当番未登録のマスは「未登録」と赤字表示する。各セル内のプルダウン（`/set-day-category/<day>` への小フォーム）で区分を手動変更できる。
