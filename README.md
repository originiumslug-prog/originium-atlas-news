# Originium Atlas 公式ニュース取得

公式サイトのiframeではなく、APIの本文・画像参照を取得し、独自ビューアーで表示する第一段階です。

## できること
- APIのタイトル・日時・カテゴリ・本文・画像参照・公式リンクを取得。
- HTML許可リストによるサニタイズ。JavaScript、iframe、任意style・イベント属性を除去。
- 新着に加えて、毎日全記事を再照合し、過去記事の訂正も検出。全件照合はページ上限内でAPIが返した件数を確認した時だけ完了扱い。
- 画像保存を有効にした場合、本文内と一覧の画像本体をSHA-256名で保存。画像失敗時は前の正常記事を残す。
- 手動実行と毎時41分の定期確認。GitHubの実行遅延・休止の可能性あり。
- 一覧取得時刻と公式の最終正常確認時刻を分けて表示。4時間超過を警告。
- 取得が部分成功ならActionsは赤にし、status.jsonへ記録。空データで一覧を消さない。

## まだ完了していないこと
- 利用者のGitHubへのアップロード・Actions実行・公開設定はまだしていません。
- 現行の約98MBの総合HTMLへの組込みはまだです。このビューアーは独立した表示試験です。
- 全過去記事の取り込み・全記事の画像検証は未実施。試験データ1記事のみで全件完了とはしません。
- 公式データの公開APIとしての継続保証、本文・画像の再配信許諾は確認できていません。公開前に条件を確認してください。公開URLが取得できることは転載許可ではありません。
- APIから消えた記事は自動削除しません。offlineTimeが過ぎた記事はビューアーで非表示ですが、APIからの消失は確認候補として扱います。
- 動画・外部ウィジェット等の埋め込みは本文から除外し、未対応表示と公式リンクを残します。「公式ページと完全に同じ表示」ではありません。
- GIFは元ファイルを保持。画像検査は署名・サイズ・ハッシュが基本で、全画像の完全デコード検証は別途必要です。

## 最初のGitHub操作（別リポジトリ推奨）
1. `originium-atlas-news` を作る。toolsとvideosは変更しません。公開／非公開は保存する本文・画像の扱いと配信方法に合わせて決めます。
2. ZIPをPCで展開し、README.md、tools、tests、webをアップロード。ZIP自体はアップロードしません。
3. GitHubのCreate new fileで `.github/workflows/sync-news.yml` を作り、同名ファイルの中身を貼る。隠しフォルダはドラッグで落ちることがあるため、明示的に作成します。
4. Actions → 日本公式ニュースの取得 → Run workflow。初回はbackfill=true、download_images=falseでテキスト取得を先に確認。
5. Actionsの成功と `web/data/index.json`、`articles/<ID>.json`、`status.json`を確認。
6. 画像の保存・配信条件と容量を確認後、Settings → Secrets and variables → Actions → Variablesへ `MIRROR_NEWS_IMAGES`=`true` を追加。これは秘密情報ではありません。再実行で画像を取得します。

画像は既定で公式URLを参照します。これは画像本体の自分管理完了ではありません。画像保存モードへの切替は別の到達点です。本文の保存自体も公開前に条件確認が必要です。

## 容量・運用
通常Gitに全画像を保存する構成は初期試験用です。1ファイル30MiB、1実行の画像合計150MiB上限。全件の容量を測り、必要なら画像を別ストレージへ分離します。無制限の素材配信や履歴肥大化を推奨しません。上限時は分割・保存先設計が必要で、同じ途中失敗を繰り返すだけでは解消しません。

通常は最新40件を毎時照合、前回の正常な全件照合から24時間を超えた実行で全件照合。遅延した場合も次の実行で再判定します。長期停止後も手動backfillを使います。APIの仕様・件数は変化するためstatus.jsonで分母と結果を確認してください。

GitHub Pagesでこのweb/フォルダを公開する設定は含めていません。Pagesを使わなくても、公開リポジトリのraw JSONを総合HTMLから読む構成にできます。非公開リポジトリのJSONは公開HTMLから匿名では読めません。PATをHTMLへ埋め込まないでください。

## ローカル検証（開発用。利用者のPCでは必須でない）
Python3.13、外部パッケージ不要。
```sh
python -m unittest discover -s tests -v
python tools/sync_news.py --pages 1
python tools/sync_news.py --backfill --pages 40 --download-images
python -m http.server 8080 --directory web
```
API: https://arknights.jp/api/resource/news/list?index=1&size=20

## 総合HTMLへの次の組込み
web/news.js・news.cssをスコープ調整して移植し、`atlasNews`のdata-indexを自分の公開index.jsonにする。旧iframeの定期読込処理と拡大・倍率設定の依存を調整し、ニュースの新UIが動画・X・他機能と干渉しないことをPC/スマホで検証する。現在のHTMLを破壊的に置換しない。
