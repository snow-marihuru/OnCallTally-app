# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

OnCallTally-app は、電話当番（オンコール）表から集計期間内の当番日数を「平日／土曜日／日祝日」区分別に人ごとへ自動集計し、Excel（.xlsx）で出力するWebアプリ。給与計算（担当日数のカウント）の手作業・ミスをなくすことが目的。単価計算は行わず、日数集計のみを担う。将来的にはWeb UIを外してローカル運用へ切り替える構想があるため、集計ロジックとUIを分離した構成にしている。

給与締めは毎月15日のため、集計期間は暦月ではなく「前月16日〜当月15日」を1サイクルとして扱う（例: 7/16〜8/15）。

人向けの使い方（セットアップ・起動・操作手順）は [README.md](README.md) に記載している。ここ（CLAUDE.md）は実装の背景や設計判断など、コードを読むだけでは分かりにくい部分の記録に絞る。

## よく使うコマンド

```bash
# 仮想環境の作成・依存インストール（初回のみ。開発時はrequirements-dev.txtでpytestも入れる）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt

# 開発サーバー起動（http://127.0.0.1:5000）
.venv/Scripts/python.exe app.py

# 自動テスト実行（tests/test_core.py。必ず `python -m pytest` で実行すること。
# `pytest` 単体だとカレントディレクトリがsys.pathに入らず `import core` に失敗する）
.venv/Scripts/python.exe -m pytest
```

`requirements.txt` / `requirements-dev.txt` はインストール済みバージョンで固定している（`pip freeze`ベース）。Flask/jpholiday/openpyxlを更新する際は、固定バージョンも合わせて更新すること。

`tests/test_core.py` は `core.py` の集計ロジック（区分自動判定・手動上書き・集計・重複/空白日検出・カレンダー生成・Excel出力・デフォルト集計期間）を固定日付でカバーしている。日付は2026年7月を中心に選んでおり、jpholiday側の祝日データが変わった場合に検出できるよう、祝日を含む日（7/20 海の日）を意図的にテストに含めている。app.py（Flask ルーティング部分）に対する自動テストは未整備で、動作確認は Flask の test_client を使って対話的に行っている。

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

## デプロイ(Render向け、デモ公開用)

本番運用ではなく一時的なデモ公開（研修アンケート提出用）を想定した最小限の対応。詳しい手順・注意点は [README.md](README.md#renderへのデモ公開について) を参照。実装上のポイントのみここに記す。

- **Procfile** : `web: gunicorn app:app --bind 0.0.0.0:$PORT`。`gunicorn app:app` のように `--bind` を省略するとgunicornは既定で `127.0.0.1:8000` にバインドしてしまい、Renderが割り当てる `$PORT` を無視するため、ヘルスチェックに失敗しデプロイが失敗する。必ず明示的にバインドすること。
- **gunicornはWindowsで動作しない**（`fcntl` に依存する純粋なUnix向けツールのため）。ローカル(Windows)での動作確認は `waitress` 等の代替WSGIサーバーで `app:app` オブジェクト自体の妥当性を検証する形にしている。gunicorn自体の起動確認はRenderの実行環境（Linux）に委ねる。
- `app.py` 末尾の `if __name__ == "__main__":` ブロックは `python app.py` で直接起動した場合のみ使われる。Render上ではgunicornが `app:app` を直接importして使うため、このブロックはRenderでは実行されない。
  - `PORT` 環境変数からポート番号を取得する（未設定時は `5000` にフォールバック）。`HOST` 環境変数は未設定時 `127.0.0.1` に**フォールバックする**（`0.0.0.0` に固定していない）。理由: Render上の実際のbindはgunicorn側の `--bind 0.0.0.0:$PORT` が行うため、この`app.run()`のhost設定はRenderの動作には影響しない。一方でここを `0.0.0.0` 固定にすると、`python app.py` で素朴にローカル起動しただけで同じLAN上の他端末からもアクセスできてしまう（認証なしで実名データを扱うため望ましくない）。ローカルLAN上の別端末から意図的に検証したい場合のみ `HOST=0.0.0.0` を明示的に設定する。
  - `FLASK_DEBUG` 環境変数が `1`/`true`/`yes`（大文字小文字を問わない）のときのみ `debug=True` かつ `use_reloader=True` にする。未設定時は両方 `False`（安全側のデフォルト）。**Render側ではこの環境変数を設定しないこと**（デバッガ経由の任意コード実行を防ぐため）。ローカルで開発時に自動リロードが欲しい場合は `FLASK_DEBUG=1` を設定して起動する。
- Renderの無料プランはアイドル後にスリープ→次回アクセスで再起動する。`SECRET_KEY` を環境変数で固定していない場合、再起動のたびにランダムな鍵が再生成され、既存のセッション（Cookieに保存された登録データ）が無効化される。データ非永続の設計自体は意図通りだが、デモ中に見た目上唐突にデータが消えるのを避けたい場合は、Renderの環境変数に `SECRET_KEY` を固定値で設定する。
